import QtQuick
import QtQuick.Layouts

// One or two time series over the last `capacity` samples, newest on the right.
Rectangle {
    id: root
    property var seriesA: []
    property var seriesB: []
    property string labelA
    property string labelB
    property color colorA: Theme.green
    property color colorB: Theme.blue
    property real minA: 0
    property real maxA: 100
    property real minB: 0
    property real maxB: 100
    property bool fillA: false
    property int capacity: 120

    color: Theme.tile
    radius: 8
    border.color: Theme.border
    implicitHeight: 92
    Layout.fillWidth: true

    onSeriesAChanged: canvas.requestPaint()
    onSeriesBChanged: canvas.requestPaint()

    RowLayout {
        id: legend
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
        spacing: 10
        Repeater {
            model: [[root.labelA, root.colorA], [root.labelB, root.colorB]]
            delegate: Row {
                required property var modelData
                visible: modelData[0] !== ""
                spacing: 4
                Rectangle {
                    width: 6; height: 6; radius: 3
                    color: parent.modelData[1]
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text { text: parent.modelData[0]; color: Theme.muted; font.pixelSize: 11 }
            }
        }
        Item { Layout.fillWidth: true }
        Text { text: root.capacity + "s"; color: Theme.dim; font.pixelSize: 10 }
    }

    Canvas {
        id: canvas
        anchors { left: parent.left; right: parent.right; top: legend.bottom; bottom: parent.bottom; margins: 8 }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        function plot(ctx, data, lo, hi, color, fill) {
            if (!data || data.length < 2) return
            var step = width / (root.capacity - 1)
            var n = data.length
            function x(i) { return width - (n - 1 - i) * step }
            function y(v) { return height - Math.max(0, Math.min(1, (v - lo) / (hi - lo))) * (height - 2) - 1 }
            ctx.beginPath()
            ctx.moveTo(x(0), y(data[0]))
            for (var i = 1; i < n; i++) ctx.lineTo(x(i), y(data[i]))
            ctx.strokeStyle = color
            ctx.lineWidth = 1.6
            ctx.lineJoin = "round"
            ctx.stroke()
            if (fill) {
                ctx.lineTo(x(n - 1), height)
                ctx.lineTo(x(0), height)
                ctx.closePath()
                var g = ctx.createLinearGradient(0, 0, 0, height)
                g.addColorStop(0, Qt.rgba(color.r, color.g, color.b, 0.35))
                g.addColorStop(1, Qt.rgba(color.r, color.g, color.b, 0.02))
                ctx.fillStyle = g
                ctx.fill()
            }
        }

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            plot(ctx, root.seriesA, root.minA, root.maxA, root.colorA, root.fillA)
            plot(ctx, root.seriesB, root.minB, root.maxB, root.colorB, false)
        }
    }
}
