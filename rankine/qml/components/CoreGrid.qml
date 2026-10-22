import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One chip per logical CPU: load percentage with a heat bar; hover shows the clock.
GridLayout {
    id: root
    property var cores: []

    Layout.fillWidth: true
    columns: Math.max(4, Math.min(16, Math.floor((width + columnSpacing) / 68)))
    columnSpacing: 6
    rowSpacing: 6

    Repeater {
        model: root.cores
        delegate: Rectangle {
            id: chip
            required property var modelData
            readonly property real load: modelData.load === null ? 0 : modelData.load

            Layout.fillWidth: true
            Layout.preferredWidth: 1
            implicitHeight: 30
            radius: 8
            color: Theme.tile
            border.color: hover.hovered ? Theme.cyan : Theme.border

            Text {
                anchors { left: parent.left; leftMargin: 7; top: parent.top; topMargin: 4 }
                text: "C" + chip.modelData.id + " " + Theme.fmt(chip.modelData.load, 0, "%")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.features: { "tnum": 1 }
            }
            Rectangle {
                anchors { left: parent.left; bottom: parent.bottom; leftMargin: 7; bottomMargin: 4 }
                height: 3
                radius: 1.5
                width: Math.max(3, (chip.width - 14) * chip.load / 100)
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.loadGradient(chip.modelData.load)[0] }
                    GradientStop { position: 1.0; color: Theme.loadGradient(chip.modelData.load)[1] }
                }
                Behavior on width { NumberAnimation { duration: 300 } }
            }

            HoverHandler { id: hover }
            ToolTip.visible: hover.hovered
            ToolTip.text: "CPU " + chip.modelData.id + " · " + Theme.fmt(chip.modelData.mhz, 0, " MHz")
        }
    }
}
