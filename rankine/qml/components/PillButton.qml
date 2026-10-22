import QtQuick

Rectangle {
    id: root
    property string text
    property color accent: Theme.text
    property bool outlined: false
    signal clicked()

    implicitWidth: label.implicitWidth + 26
    implicitHeight: 30
    radius: height / 2
    color: mouse.pressed ? Theme.track
         : outlined ? Qt.rgba(accent.r, accent.g, accent.b, mouse.containsMouse ? 0.18 : 0.10)
         : mouse.containsMouse ? Theme.borderBright : Theme.card
    border.color: outlined ? accent : Theme.border
    border.width: outlined ? 1.5 : 1

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.accent
        font.family: Theme.fontFamily
        font.pixelSize: 12
        font.weight: Font.Bold
        font.letterSpacing: 0.6
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
