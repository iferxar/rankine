import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string title
    property string subtitle
    property color subtitleColor: Theme.muted
    default property alias content: body.data

    color: Theme.card
    radius: 12
    border.color: Theme.border
    implicitHeight: column.implicitHeight + 32

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: root.title.toUpperCase()
                color: Theme.text
                font.pixelSize: 13
                font.weight: Font.DemiBold
                font.letterSpacing: 0.6
            }
            Item { Layout.fillWidth: true }
            Text {
                text: root.subtitle
                color: root.subtitleColor
                font.pixelSize: 12
                elide: Text.ElideLeft
                Layout.maximumWidth: root.width * 0.6
            }
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            spacing: 10
        }
        Item { Layout.fillHeight: true }  // keeps content top-aligned when the grid row is taller
    }
}
