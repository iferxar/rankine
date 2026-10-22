pragma Singleton
import QtQuick

QtObject {
    readonly property color bg: "#0b1119"
    readonly property color card: "#111925"
    readonly property color tile: "#162030"
    readonly property color border: "#1f2c40"
    readonly property color track: "#243247"
    readonly property color text: "#e6edf5"
    readonly property color muted: "#8a99ae"
    readonly property color dim: "#5c6b80"
    readonly property color green: "#10b981"
    readonly property color blue: "#38bdf8"
    readonly property color amber: "#f59e0b"
    readonly property color red: "#ef4444"

    function tempColor(t) {
        if (t === null || t === undefined) return muted
        return t < 65 ? green : t < 85 ? amber : red
    }

    function loadColor(p) {
        if (p === null || p === undefined) return muted
        return p < 70 ? blue : p < 90 ? amber : red
    }

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
