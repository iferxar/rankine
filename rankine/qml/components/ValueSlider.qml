import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One labelled setting: slider plus a box to type the exact value, with a tick at the default and a
// reference line (default, range, current → target). `value` is what the card reports; dragging or
// typing sets `target` until the card reports the same.
ColumnLayout {
    id: root
    property string label
    property string unit
    property real from: 0
    property real to: 1
    property real stepSize: 1
    property real value: 0
    property real defaultValue: NaN
    property real target: NaN
    property string hint            // optional extra line, e.g. how other tools show this value
    readonly property real shown: isNaN(target) ? value : target
    readonly property bool dirty: !isNaN(target) && Math.round(target) !== Math.round(value)

    function setTarget(v) {
        target = Math.max(from, Math.min(to, Math.round(v)))
    }

    onValueChanged: if (!isNaN(target) && Math.round(value) === Math.round(target)) target = NaN
    spacing: 2
    Layout.fillWidth: true

    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Text {
            text: root.label
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: 12
            Layout.fillWidth: true
        }
        Text {
            visible: !isNaN(root.defaultValue) && Math.round(root.shown) !== Math.round(root.defaultValue)
            text: (root.shown > root.defaultValue ? "+" : "") + Math.round(root.shown - root.defaultValue)
                  + " vs default"
            color: Theme.amber
            font.family: Theme.fontFamily
            font.pixelSize: 11
            font.features: { "tnum": 1 }
        }
        TextField {
            id: field
            text: Math.round(root.shown)
            enabled: !tuner.busy
            implicitWidth: 64
            horizontalAlignment: TextInput.AlignRight
            selectByMouse: true
            color: root.dirty ? Theme.cyan : Theme.text
            selectionColor: Theme.tealDeep
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.Bold
            font.features: { "tnum": 1 }
            topPadding: 3; bottomPadding: 3; leftPadding: 6; rightPadding: 6
            validator: IntValidator { bottom: Math.floor(root.from); top: Math.ceil(root.to) }
            background: Rectangle {
                radius: 6
                color: Theme.bgDeep
                border.color: field.activeFocus ? Theme.cyan : field.acceptableInput ? Theme.border : Theme.red
            }
            function commit() {
                const v = parseInt(text)
                if (!isNaN(v) && acceptableInput) root.setTarget(v)
                // Typing broke the binding; restore it so the box follows the slider again.
                text = Qt.binding(() => Math.round(root.shown))
            }
            onAccepted: { commit(); focus = false }
            onEditingFinished: commit()
            Keys.onEscapePressed: { text = Qt.binding(() => Math.round(root.shown)); focus = false }
        }
        Text {
            text: root.unit
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: 12
            Layout.preferredWidth: 28
        }
    }
    Slider {
        id: slider
        Layout.fillWidth: true
        from: root.from
        to: Math.max(root.to, root.from + 1)
        stepSize: root.stepSize
        // Mentioning from/to re-evaluates the binding when the range arrives after the value.
        value: Math.max(from, Math.min(to, root.shown))
        enabled: !tuner.busy
        onMoved: root.target = value
        background: Rectangle {
            x: slider.leftPadding
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: slider.availableWidth
            height: 6
            radius: 3
            color: Theme.track
            Rectangle {
                width: slider.visualPosition * parent.width
                height: parent.height
                radius: 3
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.teal }
                    GradientStop { position: 1.0; color: Theme.cyan }
                }
            }
            Rectangle {  // default value tick
                visible: !isNaN(root.defaultValue)
                x: (root.defaultValue - slider.from) / (slider.to - slider.from) * parent.width - 1
                anchors.verticalCenter: parent.verticalCenter
                width: 2; height: 12; radius: 1
                color: Theme.muted
            }
        }
        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: 16; height: 16; radius: 8
            color: "#ffffff"
            border.color: Theme.cyan
            border.width: 2
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Text {
            text: (isNaN(root.defaultValue) ? "" : "Default " + Math.round(root.defaultValue) + " " + root.unit + " · ")
                  + "range " + Math.round(root.from) + " to " + Math.round(root.to) + " " + root.unit
            color: Theme.dim
            font.family: Theme.fontFamily
            font.pixelSize: 11
            font.features: { "tnum": 1 }
            Layout.fillWidth: true
        }
        Text {
            visible: root.dirty
            text: "Now " + Math.round(root.value) + " → " + Math.round(root.target) + " " + root.unit
            color: Theme.cyan
            font.family: Theme.fontFamily
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.features: { "tnum": 1 }
        }
    }
    Text {
        visible: root.hint !== ""
        text: root.hint
        color: Theme.dim
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
