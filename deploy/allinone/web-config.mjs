#!/usr/bin/env node
// Generator voor de config.json van de webclient in de image (B03-017, ADR-0019).
//
// Bron: de upstream-`src/config.json` van de webclient + de eigen items van Jelly Leon (alleen webplugins onder
// `src/plugins/jellyLeon/**`). Upstream-items worden nooit weggelaten, herschikt of overschreven; eigen plugins komen
// achteraan. Zonder eigen plugins blijft het bestand byte-gelijk aan upstream (alles uit = stock-gedrag).
//
// Gebruik (in de web-bouwstap van de image; alleen Node-standaardbibliotheek):
//   node web-config.mjs --upstream src/config.json --eigen web-config.jellyleon.json --plugins-map src/plugins \
//        --uit dist/config.json [--controleer]
// Met --controleer wordt niets geschreven: het bestaande --uit-bestand wordt gecontroleerd (geen upstream-plugin
// ontbreekt, volgorde gelijk, geen onbekende plugin, overige sleutels gelijk aan upstream).
// Exitcodes: 0 = in orde, 1 = afwijking, 3 = gebruiksfout.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const EIGEN_RE = /^jellyLeon\/[A-Za-z][A-Za-z0-9]*\/plugin$/;
const EIGEN_SLEUTELS = new Set(['plugins', '_toelichting']);
const BRONEXTENSIES = ['.ts', '.tsx', '.js', '.jsx'];

function argumenten(argv) {
    const args = { controleer: false };
    for (let i = 0; i < argv.length; i++) {
        const naam = argv[i];
        if (naam === '--controleer') {
            args.controleer = true;
        } else if (['--upstream', '--eigen', '--uit', '--plugins-map'].includes(naam) && i + 1 < argv.length) {
            args[naam.slice(2)] = argv[++i];
        } else {
            throw new Error(`onbekend of onvolledig argument: ${naam}`);
        }
    }
    for (const verplicht of ['upstream', 'eigen', 'uit']) {
        if (!args[verplicht]) throw new Error(`--${verplicht} ontbreekt`);
    }
    return args;
}

function leesJson(pad, wat) {
    let tekst;
    try {
        tekst = readFileSync(pad, 'utf8');
    } catch (fout) {
        throw new Error(`${wat} ${pad} is niet leesbaar: ${fout.code ?? fout.message}`);
    }
    try {
        return { tekst, json: JSON.parse(tekst) };
    } catch {
        throw new Error(`${wat} ${pad} is geen geldige JSON`);
    }
}

function isPluginlijst(lijst) {
    return Array.isArray(lijst) && lijst.every(p => typeof p === 'string' && p.length > 0) && new Set(lijst).size === lijst.length;
}

/** Controleert de eigen items; geeft de lijst problemen (leeg = in orde). */
function controleerEigen(eigen, upstream, pluginsMap) {
    const problemen = [];
    if (eigen === null || typeof eigen !== 'object' || Array.isArray(eigen)) return ['het eigen bestand moet een JSON-object zijn'];
    for (const sleutel of Object.keys(eigen)) {
        if (!EIGEN_SLEUTELS.has(sleutel)) problemen.push(`eigen sleutel "${sleutel}" is niet toegestaan: upstream-items worden niet overschreven`);
    }
    if (!isPluginlijst(eigen.plugins ?? null)) {
        problemen.push('eigen "plugins" moet een lijst van unieke namen zijn');
        return problemen;
    }
    for (const plugin of eigen.plugins) {
        if (!EIGEN_RE.test(plugin)) {
            problemen.push(`eigen plugin "${plugin}" hoort de vorm jellyLeon/<naam>/plugin te hebben`);
        } else if (upstream.plugins.includes(plugin)) {
            problemen.push(`eigen plugin "${plugin}" staat al in de upstream-lijst`);
        } else if (pluginsMap && !BRONEXTENSIES.some(ext => existsSync(join(pluginsMap, plugin + ext)))) {
            problemen.push(`eigen plugin "${plugin}" heeft geen bronbestand onder ${pluginsMap}`);
        }
    }
    return problemen;
}

/** Controleert een bestaand resultaat tegen upstream + eigen items. */
function controleerResultaat(uit, upstream, eigen) {
    const problemen = [];
    if (!isPluginlijst(uit.json?.plugins ?? null)) return ['het resultaat heeft geen geldige "plugins"-lijst'];
    const plugins = uit.json.plugins;
    for (const plugin of upstream.json.plugins) {
        if (!plugins.includes(plugin)) problemen.push(`upstream-plugin ontbreekt: ${plugin}`);
    }
    const upstreamVolgorde = plugins.filter(p => upstream.json.plugins.includes(p));
    if (problemen.length === 0 && JSON.stringify(upstreamVolgorde) !== JSON.stringify(upstream.json.plugins)) {
        problemen.push('de volgorde van de upstream-plugins is gewijzigd');
    }
    for (const plugin of eigen.plugins) {
        if (!plugins.includes(plugin)) problemen.push(`eigen plugin ontbreekt: ${plugin}`);
    }
    for (const plugin of plugins) {
        if (!upstream.json.plugins.includes(plugin) && !eigen.plugins.includes(plugin)) problemen.push(`onbekende plugin in het resultaat: ${plugin}`);
    }
    const sleutels = new Set([...Object.keys(upstream.json), ...Object.keys(uit.json)]);
    for (const sleutel of sleutels) {
        if (sleutel !== 'plugins' && JSON.stringify(uit.json[sleutel]) !== JSON.stringify(upstream.json[sleutel])) {
            problemen.push(`sleutel "${sleutel}" wijkt af van upstream`);
        }
    }
    if (eigen.plugins.length === 0 && problemen.length === 0 && uit.tekst !== upstream.tekst) {
        problemen.push('zonder eigen plugins hoort het resultaat byte-gelijk aan upstream te zijn');
    }
    return problemen;
}

function hoofd(argv) {
    let args;
    try {
        args = argumenten(argv);
    } catch (fout) {
        console.error(`web-config: ${fout.message}`);
        return 3;
    }
    let problemen = [];
    try {
        const upstream = leesJson(args.upstream, 'upstream-config');
        if (!isPluginlijst(upstream.json?.plugins ?? null) || upstream.json.plugins.length === 0) {
            throw new Error(`upstream-config ${args.upstream} heeft geen "plugins"-lijst`);
        }
        const eigen = leesJson(args.eigen, 'eigen items').json;
        problemen = controleerEigen(eigen, upstream.json, args['plugins-map']);
        if (problemen.length === 0) {
            if (!args.controleer) {
                const tekst = eigen.plugins.length === 0
                    ? upstream.tekst
                    : JSON.stringify({ ...upstream.json, plugins: [...upstream.json.plugins, ...eigen.plugins] }, null, 2) + '\n';
                writeFileSync(args.uit, tekst);
            }
            problemen = controleerResultaat(leesJson(args.uit, 'resultaat'), upstream, eigen);
            if (problemen.length === 0) {
                const werkwoord = args.controleer ? 'gecontroleerd' : 'geschreven';
                console.log(`web-config: ${args.uit} ${werkwoord} — ${upstream.json.plugins.length} upstream-plugins, ${eigen.plugins.length} van Jelly Leon`);
            }
        }
    } catch (fout) {
        problemen = [fout.message];
    }
    for (const probleem of problemen) console.error(`web-config: ${probleem}`);
    return problemen.length === 0 ? 0 : 1;
}

process.exitCode = hoofd(process.argv.slice(2));
