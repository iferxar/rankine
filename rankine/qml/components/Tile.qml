import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string title
    property string value
    property string footer
    property bool estimated: false
    property color valueColor: Theme.text

    color: Theme.tile
    radius: 10
    border.color: hover.hovered ? Theme.borderBright : Theme.border
    implicitWidth: 120
    implicitHeight: 86
    Layout.fillWidth: true
    Layout.preferredWidth: 1

    HoverHandler { id: hover }

    // Accent notch on the left edge.
    Rectangle {
        anchors { left: parent.left; verticalCenter: parent.verticalCenter }
        width: 2
        height: parent.height * 0.42
        radius: 1
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.cyan }
            GradientStop { position: 1.0; color: Theme.teal }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        anchors.leftMargin: 12
        spacing: 2

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: root.title.toUpperCase()
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.letterSpacing: 0.8
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Rectangle {
                visible: root.estimated
                color: "#0f3a3a"
                border.color: "#14524b"
                radius: 4
                implicitWidth: est.implicitWidth + 8
                implicitHeight: est.implicitHeight + 2
                Text {
                    id: est
                    anchors.centerIn: parent
                    text: "est."
                    color: Theme.mint
                    font.family: Theme.fontFamily
                    font.pixelSize: 10
                }
            }
        }
        Text {
            text: root.value
            color: root.valueColor
            font.family: Theme.fontFamily
            font.pixelSize: 19
            font.weight: Font.Bold
            font.features: { "tnum": 1 }
        }
        Item { Layout.fillHeight: true }
        Text {
            text: root.footer
            color: Theme.dim
            font.family: Theme.fontFamily
            font.pixelSize: 10
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            lineHeight: 0.95
        }
    }
}
