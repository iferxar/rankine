pragma Singleton
import QtQuick

// Nord night backgrounds with teal / cyan / mint accents, in the spirit of the CachyOS Nord theme.
QtObject {
    readonly property color bg: "#141722"
    readonly property color bgDeep: "#0f111a"
    readonly property color card: "#1b1f2e"
    readonly property color tile: "#161926"
    readonly property color border: "#262b3f"
    readonly property color borderBright: "#323a55"
    readonly property color track: "#262c40"
    readonly property color text: "#e5e9f0"
    readonly property color muted: "#8f98ad"
    readonly property color dim: "#5f667a"

    readonly property color teal: "#00aa88"
    readonly property color tealDeep: "#008066"
    readonly property color mint: "#00ffcc"
    readonly property color cyan: "#00ccff"
    readonly property color amber: "#ffb84d"
    readonly property color orange: "#ff6a00"
    readonly property color red: "#ff4d6d"

    // Back-compat names used across components.
    readonly property color green: teal
    readonly property color blue: cyan

    readonly property string fontFamily: Qt.fontFamilies().indexOf("Fira Sans") >= 0 ? "Fira Sans" : ""

    // [start, end] gradient for a temperature.
    function tempGradient(t) {
        if (t === null || t === undefined) return [track, track]
        return t < 65 ? [teal, mint] : t < 85 ? [orange, amber] : ["#d6284b", red]
    }
    function tempColor(t) { return tempGradient(t)[1] }

    function loadGradient(p) {
        if (p === null || p === undefined) return [track, track]
        return p < 70 ? [teal, cyan] : p < 90 ? [orange, amber] : ["#d6284b", red]
    }
    function loadColor(p) { return loadGradient(p)[1] }

    function fmt(v, digits, unit) {
        if (v === null || v === undefined || isNaN(v)) return "N/A"
        return v.toFixed(digits) + (unit ? unit : "")
    }

    // "Min 50°C · Avg 55°C · Max 70°C" from a stats entry {min, avg, max}
    function range(s, digits, unit, withAvg) {
        if (!s) return "Min N/A · Max N/A"
        var parts = ["Min " + fmt(s.min, digits, unit)]
        if (withAvg) parts.push("Avg " + fmt(s.avg, digits, unit))
        parts.push("Max " + fmt(s.max, digits, unit))
        return parts.join(" · ")
    }
}
