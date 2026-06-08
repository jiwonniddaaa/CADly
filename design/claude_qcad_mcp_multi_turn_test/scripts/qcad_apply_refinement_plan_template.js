// This file is executed by QCAD with -autostart.
// It intentionally keeps the DXF operation text-based so the test can run on a minimal sample DXF.

var INPUT_DXF = __INPUT_DXF__;
var OUTPUT_DXF = __OUTPUT_DXF__;
var ROOM_LABEL_JSON = __ROOM_LABEL_JSON__;
var PLAN_JSON = __PLAN_JSON__;

function readText(path) {
    var file = new QFile(path);
    if (!file.open(QIODevice.ReadOnly | QIODevice.Text)) {
        throw "Cannot open file for read: " + path;
    }
    var stream = new QTextStream(file);
    var text = stream.readAll();
    file.close();
    return String(text);
}

function writeText(path, text) {
    var file = new QFile(path);
    if (!file.open(QIODevice.WriteOnly | QIODevice.Text)) {
        throw "Cannot open file for write: " + path;
    }
    var stream = new QTextStream(file);
    stream.writeString(text);
    file.close();
}

function readPairs(path) {
    var lines = readText(path).split(/\r?\n/);
    var pairs = [];
    for (var i = 0; i + 1 < lines.length; i += 2) {
        pairs.push([String(lines[i]).trim(), String(lines[i + 1]).trim()]);
    }
    return pairs;
}

function pairsToText(pairs) {
    var out = [];
    for (var i = 0; i < pairs.length; i++) {
        out.push(String(pairs[i][0]));
        out.push(String(pairs[i][1]));
    }
    return out.join("\n") + "\n";
}

function iterEntities(pairs) {
    var entities = [];
    var i = 0;
    while (i < pairs.length) {
        var code = pairs[i][0];
        var value = pairs[i][1];
        if (code === "0" && (value === "LINE" || value === "TEXT")) {
            var start = i;
            var etype = value;
            var data = {};
            i += 1;
            while (i < pairs.length && pairs[i][0] !== "0") {
                var c = pairs[i][0];
                if (!(c in data)) data[c] = [];
                data[c].push(pairs[i][1]);
                i += 1;
            }
            entities.push({type: etype, start: start, end: i, data: data});
            continue;
        }
        i += 1;
    }
    return entities;
}

function replaceLast(pairs, start, end, code, value) {
    for (var i = end - 1; i > start; i--) {
        if (pairs[i][0] === code) {
            pairs[i] = [code, String(value)];
            return;
        }
    }
    pairs.splice(end, 0, [code, String(value)]);
}

function lastFloat(data, code, fallback) {
    if (!(code in data) || data[code].length === 0) return fallback;
    var v = parseFloat(data[code][data[code].length - 1]);
    if (isNaN(v)) return fallback;
    return v;
}

function fmt(v) {
    var r = Math.round(v);
    if (Math.abs(v - r) < 0.000001) return String(r);
    return String(Math.round(v * 1000) / 1000);
}

function findEntitiesEndIndex(pairs) {
    var inEntities = false;
    for (var i = 0; i < pairs.length; i++) {
        if (pairs[i][0] === "2" && pairs[i][1] === "ENTITIES") {
            inEntities = true;
        }
        if (inEntities && pairs[i][0] === "0" && pairs[i][1] === "ENDSEC") {
            return i;
        }
    }
    return Math.max(0, pairs.length - 2);
}

function normalizeLayers(pairs, params) {
    var wallLayer = params.wall_layer || "WALL";
    var textLayer = params.text_layer || "ROOM_TEXT";
    var entities = iterEntities(pairs);
    var changed = 0;
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (e.type === "LINE") {
            replaceLast(pairs, e.start, e.end, "8", wallLayer);
            changed += 1;
        }
        if (e.type === "TEXT") {
            replaceLast(pairs, e.start, e.end, "8", textLayer);
            changed += 1;
        }
    }
    return changed;
}

function alignWalls(pairs, params) {
    var tol = Number(params.tolerance || 20);
    var entities = iterEntities(pairs);
    var changed = 0;
    for (var i = 0; i < entities.length; i++) {
        var e = entities[i];
        if (e.type !== "LINE") continue;
        var x1 = lastFloat(e.data, "10", 0);
        var y1 = lastFloat(e.data, "20", 0);
        var x2 = lastFloat(e.data, "11", 0);
        var y2 = lastFloat(e.data, "21", 0);
        if (Math.abs(x2 - x1) <= tol && Math.abs(y2 - y1) > tol) {
            var x = Math.round((x1 + x2) / 2);
            replaceLast(pairs, e.start, e.end, "10", fmt(x));
            replaceLast(pairs, e.start, e.end, "11", fmt(x));
            changed += 1;
        } else if (Math.abs(y2 - y1) <= tol && Math.abs(x2 - x1) > tol) {
            var y = Math.round((y1 + y2) / 2);
            replaceLast(pairs, e.start, e.end, "20", fmt(y));
            replaceLast(pairs, e.start, e.end, "21", fmt(y));
            changed += 1;
        }
    }
    return changed;
}

function addRoomLabels(pairs, params) {
    var textHeight = Number(params.text_height || 250);
    var rooms = JSON.parse(readText(ROOM_LABEL_JSON)).rooms || [];
    var insertAt = findEntitiesEndIndex(pairs);
    var newPairs = [];
    for (var i = 0; i < rooms.length; i++) {
        var r = rooms[i];
        var label = String(r.label || r.id || "room");
        var cx = Number(r.center[0]);
        var cy = Number(r.center[1]);
        newPairs.push(["0", "TEXT"]);
        newPairs.push(["8", "ROOM_TEXT"]);
        newPairs.push(["10", fmt(cx)]);
        newPairs.push(["20", fmt(cy)]);
        newPairs.push(["30", "0"]);
        newPairs.push(["40", fmt(textHeight)]);
        newPairs.push(["1", label]);
        newPairs.push(["50", "0"]);
    }
    for (var j = 0; j < newPairs.length; j++) {
        pairs.splice(insertAt + j, 0, newPairs[j]);
    }
    return rooms.length;
}

function main() {
    var plan = JSON.parse(PLAN_JSON);
    var pairs = readPairs(INPUT_DXF);
    var changed = {normalized_layers: 0, aligned_lines: 0, added_room_labels: 0};
    var actions = plan.actions || [];
    for (var i = 0; i < actions.length; i++) {
        var action = actions[i];
        var tool = action.tool;
        var params = action.params || {};
        if (tool === "normalize_layers") changed.normalized_layers += normalizeLayers(pairs, params);
        if (tool === "align_walls") changed.aligned_lines += alignWalls(pairs, params);
        if (tool === "add_room_labels") changed.added_room_labels += addRoomLabels(pairs, params);
    }
    writeText(OUTPUT_DXF, pairsToText(pairs));
    qDebug("QCAD refinement script completed: " + OUTPUT_DXF);
    qDebug(JSON.stringify(changed));
}

try {
    main();
    if (typeof qApp !== "undefined") qApp.quit();
} catch (e) {
    qDebug("QCAD refinement script failed: " + e);
    if (typeof qApp !== "undefined") qApp.exit(1);
}
