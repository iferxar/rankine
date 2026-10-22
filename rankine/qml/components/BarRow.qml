import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string label
    property string valueText
    property string accentText
    property real frac: 0
    property color barColor: Theme.blue
    property bool spinner: false
    property real spinSpeed: 0  // revolutions per second for the fan icon

    color: Theme.tile
    radius: 8
    border.color: Theme.border
    implicitHeight: 52
    Layout.fillWidth: true

    RowLayout {
        id: top
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
        spacing: 6
        Text {
            visible: root.spinner
            text: "✻"
            color: Theme.muted
            font.pixelSize: 13
            RotationAnimator on rotation {
                from: 0; to: 360
                duration: root.spinSpeed > 0 ? 1000 / root.spinSpeed : 1000
                loops: Animation.Infinite
                running: root.spinSpeed > 0
            }
        }
        Text {
            text: root.label
            color: Theme.muted
            font.pixelSize: 12
            font.weight: Font.DemiBold
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        Text { text: root.valueText; color: Theme.text; font.pixelSize: 13; font.weight: Font.Bold }
        Text {
            visible: root.accentText !== ""
            text: root.accentText
            color: root.barColor
            font.pixelSize: 13
            font.weight: Font.Bold
        }
    }

    Rectangle {
        id: track
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10 }
        height: 5
        radius: 2.5
        color: Theme.track
        Rectangle {
            height: parent.height
            radius: parent.radius
            width: parent.width * Math.max(0, Math.min(1, root.frac))
            color: root.barColor
            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
        }
    }
}
