#!/usr/bin/env node
// Converts one design canvas template (.dc.html) into a React view plus its stylesheet.
// Usage: node scripts/design-to-tsx.mjs <file.dc.html> <out-dir>
// Output is generated: change the design and re-run instead of editing View.tsx by hand.
import fs from "node:fs";
import path from "node:path";

const [source, outDir] = process.argv.slice(2);
const html = fs.readFileSync(source, "utf8");

const css = /<style>([\s\S]*?)<\/style>/.exec(html)[1];
const body = html.slice(html.indexOf("</helmet>") + "</helmet>".length, html.indexOf("</x-dc>"));

const VOID = new Set(["img", "input", "br", "hr", "meta", "link"]);
const BOOLEAN = new Set(["disabled", "checked", "readOnly", "required"]);
const ATTR_NAMES = {
  class: "className", maxlength: "maxLength", inputmode: "inputMode", tabindex: "tabIndex",
  readonly: "readOnly", autocomplete: "autoComplete", "stroke-width": "strokeWidth",
  "stroke-linecap": "strokeLinecap", "stroke-linejoin": "strokeLinejoin", "fill-rule": "fillRule",
  "clip-rule": "clipRule",
};
const ROOT_SIZE = [/width: \d+px; height: (\d+px|\{\{rootH\}\})/, "width: 100%; height: 100%"];

function tokenize(text) {
  const tokens = [];
  let i = 0;
  while (i < text.length) {
    if (text.startsWith("<!--", i)) {
      i = text.indexOf("-->", i) + 3;
      continue;
    }
    if (text[i] === "<" && /[a-zA-Z/]/.test(text[i + 1])) {
      let j = i + 1;
      let quote = null;
      for (; j < text.length; j++) {
        const c = text[j];
        if (quote) { if (c === quote) quote = null; }
        else if (c === '"' || c === "'") quote = c;
        else if (c === ">") break;
      }
      tokens.push({ type: "tag", raw: text.slice(i, j + 1) });
      i = j + 1;
      continue;
    }
    const next = text.indexOf("<", i + 1);
    const end = next === -1 ? text.length : next;
    tokens.push({ type: "text", raw: text.slice(i, end) });
    i = end;
  }
  return tokens;
}

function parseTag(raw) {
  if (raw.startsWith("</")) return { close: raw.slice(2, -1).trim() };
  const match = /^<([a-zA-Z0-9-]+)/.exec(raw);
  const name = match[1];
  const attrs = [];
  const re = /([a-zA-Z_:-]+)(?:="([^"]*)")?/g;
  re.lastIndex = match[0].length;
  const inner = raw.slice(0, raw.endsWith("/>") ? -2 : -1);
  let m;
  while ((m = re.exec(inner))) attrs.push([m[1], m[2] ?? null]);
  return { name, attrs, selfClose: raw.endsWith("/>") };
}

function tree(tokens) {
  const root = { children: [] };
  const stack = [root];
  for (const token of tokens) {
    const top = stack[stack.length - 1];
    if (token.type === "text") { top.children.push({ text: token.raw }); continue; }
    const tag = parseTag(token.raw);
    if (tag.close) {
      if (top.name !== tag.close) throw new Error(`Mismatched </${tag.close}>, open <${top.name}>`);
      stack.pop();
      continue;
    }
    const node = { ...tag, children: [] };
    top.children.push(node);
    if (!tag.selfClose && !VOID.has(tag.name)) stack.push(node);
  }
  return root;
}

const entity = (s) => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ");

const access = (hole, scope) => {
  const parts = hole.trim().split(".");
  const base = scope.has(parts[0]) ? parts[0] : `v.${parts[0]}`;
  return [base, ...parts.slice(1)].join("?.");
};

const exact = (value) => /^\{\{[^{}]+\}\}$/.test(value.trim()) ? value.trim().slice(2, -2) : null;

function templateLiteral(value, scope) {
  const out = value.replace(/\\/g, "\\\\").replace(/`/g, "\\`").replace(/\$\{/g, "\\${")
    .replace(/\{\{([^{}]+)\}\}/g, (_, h) => "${" + `${access(h, scope)} ?? ""` + "}");
  return "`" + entity(out) + "`";
}

function styleObject(value, scope) {
  const fields = [];
  for (const decl of value.split(/;(?![^(]*\))/)) {
    const colon = decl.indexOf(":");
    if (colon === -1) continue;
    const prop = decl.slice(0, colon).trim();
    const val = decl.slice(colon + 1).trim();
    const key = prop.startsWith("--") ? JSON.stringify(prop)
      : prop.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const hole = exact(val);
    if (hole) fields.push(`${key}: ${access(hole, scope)}`);
    else if (val.includes("{{")) fields.push(`${key}: ${templateLiteral(val, scope)}`);
    else fields.push(`${key}: ${JSON.stringify(entity(val))}`);
  }
  return `{{${fields.join(", ")}}}`;
}

function attribute(tag, name, value, scope) {
  if (name.startsWith("hint-")) return null;
  const jsxName = ATTR_NAMES[name] ?? name;
  if (value === null) return jsxName;
  if (name === "style") return `style=${styleObject(value, scope)}`;
  if (name === "src" && value.startsWith("/_blob/")) return "src={logo}";
  const hole = exact(value);
  if (hole) {
    const expr = access(hole, scope);
    if (BOOLEAN.has(jsxName)) return `${jsxName}={!!${expr}}`;
    if (jsxName === "value" && ["input", "textarea", "select"].includes(tag)) return `value={${expr} ?? ""}`;
    return `${jsxName}={${expr}}`;
  }
  if (value.includes("{{")) return `${jsxName}={${templateLiteral(value, scope)}}`;
  return `${jsxName}=${JSON.stringify(entity(value))}`;
}

function textChildren(raw, scope) {
  const collapsed = entity(raw).replace(/\s+/g, " ");
  const out = [];
  let last = 0;
  for (const m of collapsed.matchAll(/\{\{([^{}]+)\}\}/g)) {
    if (m.index > last) out.push(`{${JSON.stringify(collapsed.slice(last, m.index))}}`);
    out.push(`{${access(m[1], scope)}}`);
    last = m.index + m[0].length;
  }
  if (last < collapsed.length) out.push(`{${JSON.stringify(collapsed.slice(last))}}`);
  return out.join("");
}

let loopDepth = 0;
function render(nodes, scope, parent) {
  const out = [];
  nodes.forEach((node, index) => {
    if (node.text !== undefined) {
      const blank = node.text.trim() === "";
      if (blank && (index === 0 || index === nodes.length - 1 || ["select", "dl", "ul", "ol", "svg"].includes(parent))) return;
      out.push(textChildren(node.text, scope));
      return;
    }
    if (node.name === "sc-if") {
      const value = node.attrs.find(([n]) => n === "value")[1];
      out.push(`{${access(exact(value), scope)} ? (<>${render(node.children, scope, parent)}</>) : null}`);
      return;
    }
    if (node.name === "sc-for") {
      const list = node.attrs.find(([n]) => n === "list")[1];
      const as = node.attrs.find(([n]) => n === "as")[1];
      const key = `i${loopDepth++}`;
      const inner = new Set(scope).add(as);
      out.push(`{(${access(exact(list), scope)} ?? []).map((${as}: any, ${key}: number) => (<Fragment key={${key}}>${render(node.children, inner, parent)}</Fragment>))}`);
      loopDepth--;
      return;
    }
    const attrs = node.attrs.map(([n, v]) => attribute(node.name, n, v, scope)).filter(Boolean).join(" ");
    const open = `<${node.name}${attrs ? " " + attrs : ""}`;
    if (VOID.has(node.name)) out.push(`${open} />`);
    else out.push(`${open}>${render(node.children, scope, node.name)}</${node.name}>`);
  });
  return out.join("");
}

const nodes = tree(tokenize(body)).children.filter((n) => n.name || n.text.trim());
if (nodes.length !== 1) throw new Error("Expected a single root element");
const root = nodes[0];
const style = root.attrs.find(([n]) => n === "style");
style[1] = style[1].replace(ROOT_SIZE[0], ROOT_SIZE[1]);
const usesLogo = /src="\/_blob\//.test(body);

// The canvas draws a placeholder grid; the live app renders a scannable code in the same 200px box.
const QR_GRID = /\{\(v\?*\.cells \?\? \[\]\)\.map\(.*?\)\)\}/;
const QR_GRID_BOX = /gridTemplateColumns: "repeat\(25, 8px\)", gridAutoRows: "8px", /;
const finish = (code) => code.replace(QR_GRID, '<QRCodeSVG value={v.qrValue ?? ""} size={200} level="L" onClick={v.copyQr} />').replace(QR_GRID_BOX, "").replace(/"844px"/g, '"100%"').replace("onClick={v.pickDemo}", "onClick={v.pickFile}")
  .replace(/\{"(Senin, 26 Oktober 2026|Selasa, 27 Oktober 2026) · "\}/, '{v.todayText}{" · "}')
  .replace('{"26 Okt 2026, 09.02 WIB"}', "{v.scanTime}")
  .replace(/<button className="vx-btn"( style=\{\{[^}]*\}\})>\{"Unduh template"\}/, '<button onClick={v.downloadTemplate} className="vx-btn"$1>{"Unduh template"}')
  .replace(/<button className="vx-btn"( style=\{\{[^}]*\}\})>\{"Unduh daftar masalah"\}/, '<button onClick={v.downloadIssues} className="vx-btn"$1>{"Unduh daftar masalah"}')
  .replace(/<button className="vx-btn"( style=\{\{[^}]*\}\})>\{"Unduh hasil \(CSV\)"\}/, '<button onClick={v.downloadResult} className="vx-btn"$1>{"Unduh hasil (CSV)"}')
  // Record rows sit in a narrow column; their actions get a line of their own instead of being clipped.
  .replace('"128px minmax(0, 1fr) 84px 34px 92px auto"', '"128px minmax(0, 1fr) 84px 34px 92px"')
  .replace('<span style={{display: "flex", gap: "4px", justifyContent: "flex-end"}}><button onClick={r?.toggle}', '<span style={{display: "flex", gap: "4px", justifyContent: "flex-end", gridColumn: "1 / -1"}}><button onClick={r?.toggle}')
  .replace(/\{"JJK-8CF5-DC3E"\}/g, "{v.visitRef}")
  .replace('fontWeight: "700"}}>{"RS Demo Satu"}', 'fontWeight: "700"}}>{v.activeFac}')
  .replace('{"Rawat jalan · Masuk 09.02 WIB · QR terverifikasi"}', "{v.activeLine}")
  .replace('{"Kunjungan Anda di RS Demo Satu sudah tercatat."}', "{v.inText}")
  .replace('{"Kunjungan Anda di RS Demo Satu telah selesai."}', "{v.outText}");

const markup = finish(render([root], new Set(), null));
const view = `// @ts-nocheck
// Generated by scripts/design-to-tsx.mjs from ${path.basename(source)}. Do not edit by hand.
import {Fragment} from "react";
${markup.includes("QRCodeSVG") ? 'import {QRCodeSVG} from "qrcode.react";\n' : ""}${usesLogo ? 'import logo from "../assets/logo.png";\n' : ""}import "./design.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function View({v}: {v: any}) {
  return (${markup});
}
`;

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "View.tsx"), view);
fs.writeFileSync(path.join(outDir, "design.css"), `/* Generated by scripts/design-to-tsx.mjs from ${path.basename(source)}. */\n${css.trim()}\n`);
