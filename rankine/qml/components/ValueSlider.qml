import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One labelled slider with a tick at the default value. `value` is what the card reports;
// dragging sets `target` until the card reports the same.
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
    readonly property real shown: isNaN(target) ? value : target
    readonly property bool dirty: !isNaN(target) && Math.round(target) !== Math.round(value)

    onValueChanged: if (!isNaN(target) && Math.round(value) === Math.round(target)) target = NaN
    spacing: 2
    Layout.fillWidth: true

    RowLayout {
        Layout.fillWidth: true
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
        Text {
            text: Math.round(root.shown) + " " + root.unit
            color: root.dirty ? Theme.cyan : Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.Bold
            font.features: { "tnum": 1 }
            Layout.preferredWidth: 78
            horizontalAlignment: Text.AlignRight
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
}
