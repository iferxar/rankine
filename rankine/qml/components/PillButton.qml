import QtQuick

Rectangle {
    id: root
    property string text
    property color accent: Theme.text
    property bool outlined: false
    signal clicked()

    implicitWidth: label.implicitWidth + 24
    implicitHeight: 28
    radius: outlined ? height / 2 : 6
    color: mouse.pressed ? Theme.track : mouse.containsMouse ? Theme.tile : (outlined ? "transparent" : Theme.card)
    border.color: outlined ? accent : Theme.border
    border.width: outlined ? 1.5 : 1

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.accent
        font.pixelSize: 12
        font.weight: Font.DemiBold
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
