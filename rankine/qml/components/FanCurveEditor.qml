import QtQuick
import QtQuick.Layouts

// Drag the points to shape temperature -> fan speed. Speeds never drop as temperature rises.
ControlTile {
    id: root
    property string card
    property var fan: ({ mode: "auto", curve: null, percent: null })
    property var temp: null
    readonly property var defaultCurve: [[40, 20], [60, 35], [75, 55], [85, 80], [95, 100]]
    property var points: fan.curve ? fan.curve.map(p => p.slice()) : defaultCurve.map(p => p.slice())
    property bool edited: false
    readonly property real tMin: 20
    readonly property real tMax: 100

    onFanChanged: if (!edited) points = fan.curve ? fan.curve.map(p => p.slice()) : defaultCurve.map(p => p.slice())

    title: "Fan curve"
    status: (fan.mode === "curve" ? "Rankine curve" : fan.mode === "auto" ? "Firmware automatic" : fan.mode)
            + (fan.percent !== null && fan.percent !== undefined ? " · " + Math.round(fan.percent) + " %" : "")
    statusColor: fan.mode === "curve" ? Theme.mint : Theme.muted

    Item {
        id: plot
        Layout.fillWidth: true
        implicitHeight: 190
        readonly property real padL: 34
        readonly property real padB: 20
        readonly property real padT: 8
        readonly property real padR: 10
        readonly property real w: width - padL - padR
        readonly property real h: height - padT - padB
        function px(t) { return padL + (t - root.tMin) / (root.tMax - root.tMin) * w }
        function py(p) { return padT + (1 - p / 100) * h }

        Canvas {
            id: canvas
            anchors.fill: parent
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                ctx.font = "10px sans-serif"
                // grid
                ctx.strokeStyle = Theme.border
                ctx.fillStyle = Theme.dim
                ctx.lineWidth = 1
                for (let t = 20; t <= 100; t += 10) {
                    const x = plot.px(t)
                    ctx.beginPath(); ctx.moveTo(x, plot.padT); ctx.lineTo(x, plot.padT + plot.h); ctx.stroke()
                    ctx.fillText(t + "°", x - 8, plot.height - 5)
                }
                for (let p = 0; p <= 100; p += 25) {
                    const y = plot.py(p)
                    ctx.beginPath(); ctx.moveTo(plot.padL, y); ctx.lineTo(plot.padL + plot.w, y); ctx.stroke()
                    ctx.fillText(p + "%", 2, y + 3)
                }
                const pts = root.points
                if (pts.length < 2) return
                // area and line, extended flat to both edges like the helper's interpolation
                const path = [[root.tMin, pts[0][1]], ...pts, [root.tMax, pts[pts.length - 1][1]]]
                const grad = ctx.createLinearGradient(0, plot.padT, 0, plot.padT + plot.h)
                grad.addColorStop(0, Qt.rgba(0, 0.8, 1, 0.28))
                grad.addColorStop(1, Qt.rgba(0, 0.67, 0.53, 0.02))
                ctx.beginPath()
                ctx.moveTo(plot.px(path[0][0]), plot.py(0))
                for (const [t, p] of path) ctx.lineTo(plot.px(t), plot.py(p))
                ctx.lineTo(plot.px(path[path.length - 1][0]), plot.py(0))
                ctx.closePath()
                ctx.fillStyle = grad
                ctx.fill()
                ctx.beginPath()
                path.forEach(([t, p], i) => i ? ctx.lineTo(plot.px(t), plot.py(p)) : ctx.moveTo(plot.px(t), plot.py(p)))
                ctx.strokeStyle = Theme.cyan
                ctx.lineWidth = 2
                ctx.stroke()
                // current reading
                if (root.temp !== null && root.temp !== undefined) {
                    const x = plot.px(Math.max(root.tMin, Math.min(root.tMax, root.temp)))
                    ctx.setLineDash([3, 3])
                    ctx.strokeStyle = Theme.amber
                    ctx.lineWidth = 1
                    ctx.beginPath(); ctx.moveTo(x, plot.padT); ctx.lineTo(x, plot.padT + plot.h); ctx.stroke()
                    ctx.setLineDash([])
                    if (root.fan.percent !== null && root.fan.percent !== undefined) {
                        ctx.fillStyle = Theme.amber
                        ctx.beginPath(); ctx.arc(x, plot.py(root.fan.percent), 4, 0, 2 * Math.PI); ctx.fill()
                    }
                }
                // handles
                for (let i = 0; i < pts.length; i++) {
                    ctx.beginPath()
                    ctx.arc(plot.px(pts[i][0]), plot.py(pts[i][1]), i === drag.index ? 7 : 5.5, 0, 2 * Math.PI)
                    ctx.fillStyle = "#ffffff"
                    ctx.fill()
                    ctx.strokeStyle = Theme.teal
                    ctx.lineWidth = 2
                    ctx.stroke()
                }
            }
        }

        Connections {
            target: root
            function onPointsChanged() { canvas.requestPaint() }
            function onTempChanged() { canvas.requestPaint() }
            function onFanChanged() { canvas.requestPaint() }
        }
        onWidthChanged: canvas.requestPaint()

        MouseArea {
            id: drag
            anchors.fill: parent
            enabled: !tuner.busy
            property int index: -1
            cursorShape: index >= 0 ? Qt.ClosedHandCursor : Qt.ArrowCursor
            onPressed: mouse => {
                let best = -1, bestD = 16
                root.points.forEach(([t, p], i) => {
                    const d = Math.hypot(plot.px(t) - mouse.x, plot.py(p) - mouse.y)
                    if (d < bestD) { best = i; bestD = d }
                })
                index = best
                mouse.accepted = best >= 0
                canvas.requestPaint()
            }
            onPositionChanged: mouse => {
                if (index < 0) return
                const pts = root.points.map(p => p.slice())
                const prev = pts[index - 1], next = pts[index + 1]
                let t = root.tMin + (mouse.x - plot.padL) / plot.w * (root.tMax - root.tMin)
                let p = (1 - (mouse.y - plot.padT) / plot.h) * 100
                t = Math.round(Math.max(prev ? prev[0] + 1 : root.tMin, Math.min(next ? next[0] - 1 : root.tMax, t)))
                p = Math.round(Math.max(prev ? prev[1] : 0, Math.min(next ? next[1] : 100, p)))
                pts[index] = [t, p]
                root.points = pts
                root.edited = true
            }
            onReleased: { index = -1; canvas.requestPaint() }
        }
    }

    Text {
        text: root.points.map(p => p[0] + "° → " + p[1] + "%").join("   ")
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: 11
        font.features: { "tnum": 1 }
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Text {
            text: "Edge temperature drives the curve; above 100 °C hotspot the fan goes to 100 %. "
                  + "Firmware mode keeps zero-RPM at idle."
            color: Theme.dim
            font.family: Theme.fontFamily
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        PillButton {
            text: "Firmware auto"
            visible: root.fan.mode !== "auto"
            onClicked: { root.edited = false; tuner.setFanAuto(root.card) }
        }
        PillButton {
            text: "Reset points"
            visible: root.edited
            onClicked: { root.edited = false; root.points = root.fan.curve ? root.fan.curve.map(p => p.slice()) : root.defaultCurve.map(p => p.slice()) }
        }
        PillButton {
            text: root.fan.mode === "curve" ? "Apply changes" : "Use this curve"
            outlined: true
            accent: Theme.mint
            visible: root.edited || root.fan.mode !== "curve"
            onClicked: { root.edited = false; tuner.setFanCurve(root.card, root.points) }
        }
    }
}
