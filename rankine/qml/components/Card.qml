import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string title
    property string subtitle
    property color subtitleColor: Theme.muted
    default property alias content: body.data

    color: Theme.card
    radius: 14
    border.color: Theme.border
    implicitHeight: column.implicitHeight + 34
    clip: true

    // Thin accent line along the top edge.
    Rectangle {
        anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: 18; rightMargin: 18 }
        height: 2
        radius: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Theme.teal }
            GradientStop { position: 0.45; color: Theme.cyan }
            GradientStop { position: 1.0; color: "transparent" }
        }
        opacity: 0.85
    }

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: 16
        anchors.topMargin: 18
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Facet { size: 13 }
            Text {
                text: root.title.toUpperCase()
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.Bold
                font.letterSpacing: 1.2
            }
            Item { Layout.fillWidth: true }
            Text {
                text: root.subtitle
                color: root.subtitleColor
                font.family: Theme.fontFamily
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
