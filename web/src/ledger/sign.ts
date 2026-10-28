/**
 * Investigator keys and signed decisions (see atlas/signing.py). The private key is an Ed25519 WebCrypto key created
 * non-extractable: this browser can sign with it, but no script can read it out. The public key is what the audit
 * office enrols. A statement is a flat object of strings, signed as canonical JSON (keys sorted, no spaces, UTF-8).
 */
import { canonicalOf } from "./verify";

export const STATEMENT_KEYS = ["run", "case", "decision", "challenge", "note", "verdict", "verdict_reason", "verdict_entry",
  "ledger_head", "key_id", "signed_at", "site"] as const;
export type Statement = Record<(typeof STATEMENT_KEYS)[number], string>;

export const CHALLENGES: Record<string, string> = {
  WRONG_SITE: "The works are at another reach than the one the verdict was read on.",
  EXISTING_STRUCTURE_WORKED_ON: "The contract repaired, raised or extended a structure that was already there.",
  WRONG_READING: "A capture reading is wrong: the imagery shows something else.",
  OTHER: "Another reason, in the note.",
};

const b64 = (b: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(b)));
const unb64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const hex = (b: ArrayBuffer) => Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("");

export async function keyId(publicKey: string): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", unb64(publicKey))).slice(0, 16);
}

export function message(st: Statement): Uint8Array {
  const flat: Record<string, string> = {};
  for (const k of STATEMENT_KEYS) flat[k] = st[k] ?? "";
  return new TextEncoder().encode(canonicalOf(flat));
}

function idb(): Promise<IDBDatabase> {
  return new Promise((ok, fail) => {
    const r = indexedDB.open("atlas-investigator", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("keys");
    r.onsuccess = () => ok(r.result);
    r.onerror = () => fail(r.error);
  });
}

export type MyKey = { pair: CryptoKeyPair; publicKey: string; keyId: string };

/** This browser's investigator key, created on first use. */
export async function myKey(): Promise<MyKey> {
  const db = await idb();
  const got = await new Promise<CryptoKeyPair | undefined>((ok) => {
    const q = db.transaction("keys").objectStore("keys").get("me");
    q.onsuccess = () => ok(q.result as CryptoKeyPair | undefined);
    q.onerror = () => ok(undefined);
  });
  let pair = got;
  if (!pair) {
    pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"])) as CryptoKeyPair;
    await new Promise((ok) => {
      const tx = db.transaction("keys", "readwrite");
      tx.objectStore("keys").put(pair, "me");
      tx.oncomplete = ok;
    });
  }
  const publicKey = b64(await crypto.subtle.exportKey("raw", pair.publicKey));
  return { pair, publicKey, keyId: await keyId(publicKey) };
}

export async function signStatement(k: MyKey, st: Statement): Promise<string> {
  return b64(await crypto.subtle.sign({ name: "Ed25519" }, k.pair.privateKey, message(st)));
}

/** Check a sealed decision with no Atlas server: the signature against the key it carries, and the key's id. */
export async function verifyDecision(p: { statement?: Statement; public_key?: string; signature?: string }): Promise<boolean> {
  if (!p.statement || !p.public_key || !p.signature) return false;
  if ((await keyId(p.public_key)) !== p.statement.key_id) return false;
  try {
    const key = await crypto.subtle.importKey("raw", unb64(p.public_key), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, unb64(p.signature), message(p.statement));
  } catch {
    return false;
  }
}
