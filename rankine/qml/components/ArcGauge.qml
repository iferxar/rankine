import QtQuick

// 270° arc gauge with a glowing gradient arc, tick ring, value in the middle and a min/max line underneath.
Item {
    id: root
    property real value: 0
    property real minValue: 0
    property real maxValue: 100
    property var colors: [Theme.teal, Theme.mint]
    property string valueText
    property string label
    property bool coloredLabel: false
    property string footer
    property real thickness: 11

    implicitWidth: 150
    implicitHeight: 160

    property real shown: Math.max(0, Math.min(1, (value - minValue) / (maxValue - minValue)))
    Behavior on shown { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
    onShownChanged: canvas.requestPaint()
    onColorsChanged: canvas.requestPaint()

    readonly property real dialSize: Math.min(width, height - footerText.height)

    Canvas {
        id: canvas
        width: root.dialSize
        height: root.dialSize
        anchors.horizontalCenter: parent.horizontalCenter
        onWidthChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var cx = width / 2, cy = height / 2
            var r = width / 2 - root.thickness / 2 - 10  // room for the glow inside the canvas
            var a0 = 0.75 * Math.PI, sweep = 1.5 * Math.PI

            // Tick ring inside the arc.
            ctx.strokeStyle = Theme.borderBright
            ctx.lineWidth = 1
            for (var i = 0; i <= 18; i++) {
                var a = a0 + sweep * i / 18
                var inner = r - root.thickness / 2 - (i % 3 === 0 ? 8 : 5)
                var outer = r - root.thickness / 2 - 3
                ctx.beginPath()
                ctx.moveTo(cx + inner * Math.cos(a), cy + inner * Math.sin(a))
                ctx.lineTo(cx + outer * Math.cos(a), cy + outer * Math.sin(a))
                ctx.stroke()
            }

            ctx.lineCap = "round"
            ctx.lineWidth = root.thickness
            ctx.strokeStyle = Theme.track
            ctx.beginPath()
            ctx.arc(cx, cy, r, a0, a0 + sweep, false)
            ctx.stroke()

            if (root.shown > 0.004) {
                var g = ctx.createLinearGradient(0, height, width, 0)
                g.addColorStop(0, root.colors[0])
                g.addColorStop(1, root.colors[1])
                ctx.strokeStyle = g
                var c = root.colors[1]
                ctx.shadowColor = Qt.rgba(c.r, c.g, c.b, 0.5)
                ctx.shadowBlur = 9
                ctx.beginPath()
                ctx.arc(cx, cy, r, a0, a0 + sweep * root.shown, false)
                ctx.stroke()

                // Bright dot at the tip, like the bubbles in the CachyOS artwork.
                var tip = a0 + sweep * root.shown
                ctx.shadowBlur = 10
                ctx.fillStyle = "#ffffff"
                ctx.beginPath()
                ctx.arc(cx + r * Math.cos(tip), cy + r * Math.sin(tip), root.thickness * 0.22, 0, 2 * Math.PI)
                ctx.fill()
            }
        }

        Column {
            anchors.centerIn: parent
            spacing: 2
            // "55°C" -> big "55" and a smaller "°C" sharing the baseline.
            Row {
                id: valueRow
                readonly property var parts: (root.valueText.match(/^(-?[\d.]+)(.*)$/) || [null, root.valueText, ""])
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 1
                Text {
                    id: number
                    text: valueRow.parts[1]
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Math.max(16, canvas.width * 0.2)
                    font.weight: Font.Bold
                }
                Text {
                    text: valueRow.parts[2]
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: number.font.pixelSize * 0.5
                    font.weight: Font.DemiBold
                    anchors.baseline: number.baseline
                }
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 5
                Rectangle {
                    visible: root.coloredLabel
                    width: 6; height: 6; radius: 3
                    color: root.colors[1]
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: root.label.toUpperCase()
                    color: root.coloredLabel ? root.colors[1] : Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1
                }
            }
        }
    }

    Text {
        id: footerText
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: canvas.bottom
        anchors.topMargin: -canvas.height * 0.09
        text: root.footer
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: 11
    }
}
