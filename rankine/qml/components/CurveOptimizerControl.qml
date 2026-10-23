import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Per-core Curve Optimizer margins. Negative counts lower each core's voltage-frequency curve.
ControlTile {
    id: root
    property var cpu: ({})
    readonly property var co: cpu.co || []
    readonly property var boot: (cpu.boot || {}).co || []
    readonly property var range: cpu.co_range || [-30, 0]
    property var edits: null          // margins being edited, until the CPU reports them
    readonly property var shown: edits || co
    readonly property bool dirty: !!edits && edits.some((m, i) => m !== co[i])

    function setAll(m) { edits = co.map(() => m) }
    function setCore(i, m) {
        const e = (edits || co).slice()
        e[i] = m
        edits = e
    }
    function sameAs(a, b) { return a.length === b.length && a.every((m, i) => m === b[i]) }

    onCoChanged: if (edits && sameAs(edits, co)) edits = null

    title: "Curve Optimizer"
    status: !cpu.co_readable ? "Unavailable"
          : co.every(m => m === co[0]) ? "All cores " + (co[0] ?? 0) : "Per core"
    statusColor: cpu.co_readable ? Theme.mint : Theme.amber

    Text {
        visible: !root.cpu.co_readable
        text: "The current margins cannot be read back (" + (root.cpu.co_error || "unknown error")
              + "), so Rankine could not restore them; Curve Optimizer stays off."
        color: Theme.amber
        font.family: Theme.fontFamily
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    ValueSlider {
        id: all
        visible: !!root.cpu.co_readable
        label: "All cores"
        unit: ""
        from: root.range[0]; to: root.range[1]
        value: root.co.length ? root.co[0] : 0
        defaultValue: root.boot.length ? root.boot[0] : NaN
        hint: "Each negative count lowers the core's voltage by a few millivolts at the same clock. Start "
              + "around -5 to -10 for all cores and go down in steps; the best cores usually take the least."
        onTargetChanged: if (!isNaN(target)) root.setAll(Math.round(target))
    }

    GridLayout {
        visible: !!root.cpu.co_readable && !!root.cpu.per_core
        Layout.fillWidth: true
        columns: 8
        columnSpacing: 6
        rowSpacing: 6
        Repeater {
            model: root.co.length
            delegate: ColumnLayout {
                required property int index
                readonly property bool changed: root.shown[index] !== root.co[index]
                spacing: 1
                Layout.fillWidth: true
                Text {
                    text: "C" + index
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: 10
                    Layout.alignment: Qt.AlignHCenter
                }
                TextField {
                    id: box
                    Layout.fillWidth: true
                    text: root.shown[index] ?? 0
                    horizontalAlignment: TextInput.AlignHCenter
                    enabled: !tuner.busy
                    selectByMouse: true
                    color: parent.changed ? Theme.cyan : Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    font.weight: Font.Bold
                    topPadding: 3; bottomPadding: 3; leftPadding: 2; rightPadding: 2
                    validator: IntValidator { bottom: root.range[0]; top: root.range[1] }
                    background: Rectangle {
                        radius: 5
                        color: Theme.bgDeep
                        border.color: box.activeFocus ? Theme.cyan : box.acceptableInput ? Theme.border : Theme.red
                    }
                    function commit() {
                        const v = parseInt(text)
                        if (!isNaN(v) && acceptableInput) root.setCore(index, v)
                        text = Qt.binding(() => root.shown[index] ?? 0)
                    }
                    onAccepted: { commit(); focus = false }
                    onEditingFinished: commit()
                }
            }
        }
    }
    Text {
        visible: !!root.cpu.co_readable && !root.cpu.per_core
        text: "This CPU has cores fused off, so the SMU's core numbering cannot be matched safely: only one margin for all cores is offered."
        color: Theme.dim
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: root.dirty
        text: "Undervolting the CPU can cause crashes, freezes or silent calculation errors. Change a few counts at a time "
              + "and test each step under load and in normal use. Settings reset on reboot unless applied at boot."
        color: Theme.amber
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        visible: !!root.cpu.co_readable
        Layout.fillWidth: true
        spacing: 8
        Item { Layout.fillWidth: true }
        PillButton {
            text: "Defaults"
            visible: !root.sameAs(root.shown, root.boot)
            onClicked: { all.target = NaN; root.edits = root.boot.slice() }
        }
        PillButton {
            text: "Cancel"
            visible: !!root.edits
            onClicked: { all.target = NaN; root.edits = null }
        }
        PillButton {
            text: "Apply"
            outlined: true
            accent: Theme.mint
            visible: root.dirty
            onClicked: { all.target = NaN; tuner.setCurveOptimizer(root.edits) }
        }
    }
}
