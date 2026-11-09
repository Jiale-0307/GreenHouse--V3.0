import { getHash, stripHash, toFileSystemPath } from "./url.js";
const nonJsonTypes = ["function", "symbol", "undefined"];
const protectedProps = ["constructor", "prototype", "__proto__"];
const objectPrototype = Object.getPrototypeOf({});
/**
 * Custom JSON serializer for Error objects.
 * Returns all built-in error properties, as well as extended properties.
 */
export function toJSON() {
    // HACK: We have to cast the objects to `any` so we can use symbol indexers.
    // see https://github.com/Microsoft/TypeScript/issues/1863
    const pojo = {};
    const error = this;
    for (const key of getDeepKeys(error)) {
        if (typeof key === "string") {
            const value = error[key];
            const type = typeof value;
            if (!nonJsonTypes.includes(type)) {
                pojo[key] = value;
            }
        }
    }
    return pojo;
}
/**
 * Returns own, inherited, enumerable, non-enumerable, string, and symbol keys of `obj`.
 * Does NOT return members of the base Object prototype, or the specified omitted keys.
 */
export function getDeepKeys(obj, omit = []) {
    let keys = [];
    // Crawl the prototype chain, finding all the string and symbol keys
    while (obj && obj !== objectPrototype) {
        keys = keys.concat(Object.getOwnPropertyNames(obj), Object.getOwnPropertySymbols(obj));
        obj = Object.getPrototypeOf(obj);
    }
    // De-duplicate the list of keys
    const uniqueKeys = new Set(keys);
    // Remove any omitted keys
    for (const key of omit.concat(protectedProps)) {
        uniqueKeys.delete(key);
    }
    return uniqueKeys;
}
export class JSONParserError extends Error {
    name;
    message;
    source;
    path;
    code;
    constructor(message, source, options) {
        super(undefined, options);
        this.code = "EUNKNOWN";
        this.name = "JSONParserError";
        this.message = message;
        this.source = source;
        this.path = null;
    }
    toJSON = toJSON.bind(this);
    get footprint() {
        return `${this.path}+${this.source}+${this.code}+${this.message}`;
    }
}
export class JSONParserErrorGroup extends Error {
    files;
    constructor(parser) {
        super();
        this.files = parser;
        this.name = "JSONParserErrorGroup";
        this.message = `${this.errors.length} error${this.errors.length > 1 ? "s" : ""} occurred while reading '${toFileSystemPath(parser.$refs._root$Ref.path)}'`;
    }
    toJSON = toJSON.bind(this);
    static getParserErrors(parser) {
        const errors = [];
        const footprints = new Set();
        const refs = [
            ...Object.values(parser.$refs._$refs),
            ...Object.values(parser.$refs._aliases),
        ];
        for (const $ref of refs) {
            if ($ref.errors) {
                for (const error of $ref.errors) {
                    if (!footprints.has(error.footprint)) {
                        footprints.add(error.footprint);
                        errors.push(error);
                    }
                }
            }
        }
        return errors;
    }
    get errors() {
        return JSONParserErrorGroup.getParserErrors(this.files);
    }
}
export class ParserError extends JSONParserError {
    code = "EPARSER";
    name = "ParserError";
    constructor(message, source, options) {
        super(`Error parsing ${source}: ${message}`, source, options);
    }
}
export class UnmatchedParserError extends JSONParserError {
    code = "EUNMATCHEDPARSER";
    name = "UnmatchedParserError";
    constructor(source) {
        super(`Could not find parser for "${source}"`, source);
    }
}
export class ResolverError extends JSONParserError {
    code = "ERESOLVER";
    name = "ResolverError";
    ioErrorCode;
    constructor(ex, source, options) {
        super(ex.message || `Error reading file "${source}"`, source, options);
        if ("code" in ex) {
            this.ioErrorCode = String(ex.code);
        }
    }
}
export class UnmatchedResolverError extends JSONParserError {
    code = "EUNMATCHEDRESOLVER";
    name = "UnmatchedResolverError";
    constructor(source) {
        super(`Could not find resolver for "${source}"`, source);
    }
}
export class MissingPointerError extends JSONParserError {
    code = "EMISSINGPOINTER";
    name = "MissingPointerError";
    targetToken;
    targetRef;
    targetFound;
    parentPath;
    constructor(token, path, targetRef, targetFound, parentPath) {
        super(`Missing $ref pointer "${getHash(path)}". Token "${token}" does not exist.`, stripHash(path));
        this.targetToken = token;
        this.targetRef = targetRef;
        this.targetFound = targetFound;
        this.parentPath = parentPath;
    }
}
export class TimeoutError extends JSONParserError {
    code = "ETIMEOUT";
    name = "TimeoutError";
    constructor(timeout) {
        super(`Dereferencing timeout reached: ${timeout}ms`);
    }
}
export class InvalidPointerError extends JSONParserError {
    code = "EINVALIDPOINTER";
    name = "InvalidPointerError";
    constructor(pointer, path) {
        super(`Invalid $ref pointer "${pointer}". Pointers must begin with "#/"`, stripHash(path));
    }
}
export function isHandledError(err) {
    return err instanceof JSONParserError || err instanceof JSONParserErrorGroup;
}
export function normalizeError(err) {
    if (err.path === null) {
        err.path = [];
    }
    return err;
}
