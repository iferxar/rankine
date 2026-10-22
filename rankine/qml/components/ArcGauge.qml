import QtQuick
import QtQuick.Shapes

// 270° arc gauge with the value in the middle and a min/max line underneath.
Item {
    id: root
    property real value: 0
    property real minValue: 0
    property real maxValue: 100
    property color color: Theme.green
    property string valueText
    property string label
    property bool coloredLabel: false
    property string footer
    property real thickness: 11

    implicitWidth: 150
    implicitHeight: 160

    property real shown: Math.max(0, Math.min(1, (value - minValue) / (maxValue - minValue)))
    Behavior on shown { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }

    readonly property real dialSize: Math.min(width, height - footerText.height)

    Item {
        id: dial
        width: root.dialSize
        height: root.dialSize
        anchors.horizontalCenter: parent.horizontalCenter
        readonly property real r: width / 2 - root.thickness / 2

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                strokeColor: Theme.track
                strokeWidth: root.thickness
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: dial.width / 2; centerY: dial.height / 2
                    radiusX: dial.r; radiusY: dial.r
                    startAngle: 135; sweepAngle: 270
                }
            }
            ShapePath {
                strokeColor: root.shown > 0.004 ? root.color : "transparent"
                strokeWidth: root.thickness
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: dial.width / 2; centerY: dial.height / 2
                    radiusX: dial.r; radiusY: dial.r
                    startAngle: 135; sweepAngle: 270 * root.shown
                }
            }
        }

        Column {
            anchors.centerIn: parent
            spacing: 2
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.valueText
                color: Theme.text
                font.pixelSize: Math.max(16, dial.width * 0.19)
                font.weight: Font.Bold
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 5
                Rectangle {
                    visible: root.coloredLabel
                    width: 6; height: 6; radius: 3
                    color: root.color
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: root.label.toUpperCase()
                    color: root.coloredLabel ? root.color : Theme.muted
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
            }
        }
    }

    Text {
        id: footerText
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: dial.bottom
        anchors.topMargin: -dial.height * 0.08
        text: root.footer
        color: Theme.muted
        font.pixelSize: 11
    }
}
