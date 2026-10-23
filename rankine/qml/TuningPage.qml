import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

// What Rankine can tune on this machine; live GPU controls when rankine-tuned is running.
ScrollView {
    id: page
    contentWidth: availableWidth

    readonly property var t: tuner.report
    readonly property var helper: t.helper || ({})
    readonly property var cards: (tuner.state.cards) || ({})
    readonly property var helperFeature: helper.running
        ? { title: "Helper service", state: "ready",
            detail: "rankine-tuned is running on the " + helper.bus + " bus. Every change asks for your password, "
                    + "and reverts after a few seconds unless you keep it." }
        : helper.installed
        ? { title: "Helper service", state: "setup",
            detail: "rankine-tuned is installed but not running. This page works without it; tuning will need it.",
            command: "sudo systemctl enable --now rankine-tuned.service" }
        : { title: "Helper service", state: "setup",
            detail: "rankine-tuned is not installed. This page works without it; tuning will need it.",
            fix: "From the Rankine checkout, install the system files, then enable the service:",
            command: "sudo ./scripts/install-tuned.sh && sudo systemctl enable --now rankine-tuned.service" }

    Item {
        width: page.availableWidth
        implicitHeight: grid.implicitHeight + 32 + (tuner.state.pending ? 90 : 0)  // room for the toast

        GridLayout {
            id: grid
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            columns: width > 1000 ? 2 : 1
            columnSpacing: 16
            rowSpacing: 16
            uniformCellWidths: true

            Card {
                title: "Tuning"
                subtitle: page.helper.running ? "CHANGES REVERT UNLESS KEPT" : "READ-ONLY"
                subtitleColor: Theme.amber
                Layout.columnSpan: grid.columns
                Layout.fillWidth: true

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    Text {
                        text: "What Rankine can tune on this machine, and what each feature still needs. "
                            + "Versions refer to the roadmap in docs/TUNING.md. Settings last until reboot or "
                            + "until the helper stops; nothing is applied at boot."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    PillButton { text: "Refresh"; onClicked: tuner.refresh() }
                }
                FeatureRow { feature: page.helperFeature }
                Text {
                    visible: tuner.busy || tuner.message !== ""
                    text: tuner.busy ? "Waiting for authorization…" : "Couldn't apply: " + tuner.message
                    color: tuner.busy ? Theme.amber : Theme.red
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                ComparisonTile {
                    visible: !!tuner.comparison.what
                    comparison: tuner.comparison
                }
            }

            Repeater {
                model: page.t.gpus || []
                delegate: Card {
                    id: gpuCard
                    required property var modelData
                    readonly property var live: page.cards[modelData.card]
                    title: "Graphics"
                    subtitle: modelData.name
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop

                    PowerControl {
                        visible: !!gpuCard.live && !!gpuCard.live.power
                        card: gpuCard.modelData.card
                        power: gpuCard.live && gpuCard.live.power ? gpuCard.live.power : ({ cap: 0, min: 0, max: 1, default: 0 })
                    }
                    PerformanceControl {
                        visible: !!gpuCard.live && !!gpuCard.live.level
                        card: gpuCard.modelData.card
                        level: gpuCard.live ? gpuCard.live.level || "" : ""
                        profiles: gpuCard.live ? gpuCard.live.profiles : []
                        profile: gpuCard.live && gpuCard.live.profile !== null ? gpuCard.live.profile : -1
                    }
                    FanCurveEditor {
                        visible: !!gpuCard.live && gpuCard.live.fan.percent !== null
                        card: gpuCard.modelData.card
                        fan: gpuCard.live ? gpuCard.live.fan : ({ mode: "auto", curve: null, percent: null })
                        temp: gpuCard.live ? gpuCard.live.temp : null
                    }
                    // Without the helper, or for what it cannot control yet, explain instead.
                    Repeater {
                        model: gpuCard.modelData.features.filter(f => !gpuCard.live
                            || ["gpu-power", "gpu-profile", "gpu-fan"].indexOf(f.id) < 0)
                        delegate: FeatureRow { required property var modelData; feature: modelData }
                    }
                    RowLayout {
                        visible: !!gpuCard.live && gpuCard.live.changed
                        Layout.fillWidth: true
                        Text {
                            text: "Changed by Rankine since the helper started."
                            color: Theme.dim
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                            Layout.fillWidth: true
                        }
                        PillButton { text: "Restore original settings"; onClicked: tuner.reset(gpuCard.modelData.card) }
                    }
                }
            }

            Card {
                visible: !!page.t.cpu
                title: "Processor"
                subtitle: page.t.cpu ? page.t.cpu.name + (page.t.cpu.codename ? " · " + page.t.cpu.codename : "") : ""
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                Repeater {
                    model: page.t.cpu ? page.t.cpu.features : []
                    delegate: FeatureRow { required property var modelData; feature: modelData }
                }
            }

            Card {
                visible: (page.t.tools || []).length > 0
                title: "Stability testing"
                subtitle: "TOOLS"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                Repeater {
                    model: page.t.tools || []
                    delegate: FeatureRow { required property var modelData; feature: modelData }
                }
            }
        }
    }
}
