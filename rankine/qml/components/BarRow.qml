import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string label
    property string valueText
    property string accentText
    property real frac: 0
    property var colors: [Theme.teal, Theme.cyan]
    property bool spinner: false
    property real spinSpeed: 0  // revolutions per second for the fan icon

    color: Theme.tile
    radius: 10
    border.color: Theme.border
    implicitHeight: 52
    Layout.fillWidth: true

    RowLayout {
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10; leftMargin: 12 }
        spacing: 8
        Facet {
            visible: root.spinner
            size: 12
            opacity: root.spinSpeed > 0 ? 1 : 0.35
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
            font.family: Theme.fontFamily
            font.pixelSize: 12
            font.weight: Font.DemiBold
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        Text {
            text: root.valueText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.Bold
            font.features: { "tnum": 1 }
        }
        Text {
            visible: root.accentText !== ""
            text: root.accentText
            color: root.colors[1]
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.Bold
        }
    }

    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10; leftMargin: 12 }
        height: 6
        radius: 3
        color: Theme.track
        Rectangle {
            id: fill
            height: parent.height
            radius: parent.radius
            width: parent.width * Math.max(0, Math.min(1, root.frac))
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: root.colors[0] }
                GradientStop { position: 1.0; color: root.colors[1] }
            }
            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
        }
        // Glowing bead at the end of the bar.
        Rectangle {
            visible: root.frac > 0.01
            width: 10; height: 10; radius: 5
            x: fill.width - width / 2
            anchors.verticalCenter: parent.verticalCenter
            color: "#ffffff"
            border.color: root.colors[1]
            border.width: 2
        }
    }
}
