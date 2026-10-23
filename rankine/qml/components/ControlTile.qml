import QtQuick
import QtQuick.Layouts

// Frame for a live tuning control: title, a short status on the right, then the control itself.
Rectangle {
    id: root
    property string title
    property string status
    property color statusColor: Theme.muted
    default property alias content: body.data

    color: Theme.tile
    radius: 10
    border.color: Theme.border
    implicitHeight: column.implicitHeight + 20
    Layout.fillWidth: true

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10; leftMargin: 12 }
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle { width: 8; height: 8; radius: 4; color: Theme.mint }
            Text {
                text: root.title
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.Bold
                Layout.fillWidth: true
            }
            Text {
                text: root.status
                color: root.statusColor
                font.family: Theme.fontFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
                font.features: { "tnum": 1 }
            }
        }
        ColumnLayout {
            id: body
            Layout.fillWidth: true
            Layout.leftMargin: 16
            spacing: 8
        }
    }
}
