import type { Options, ParserOptions } from "./options.js";
import type { JSONSchema, SchemaCallback } from "./index.js";
export interface NormalizedArguments<S extends object = JSONSchema, O extends ParserOptions<S> = ParserOptions<S>> {
    path: string;
    schema: S | boolean | undefined;
    options: O & Options<S>;
    callback: SchemaCallback<S>;
}
/**
 * Normalizes the given arguments, accounting for optional args.
 * Operations that delegate to parse can defer cloning until that call.
 */
export declare function normalizeArgs<S extends object = JSONSchema, O extends ParserOptions<S> = ParserOptions<S>>(_args: Partial<IArguments>, cloneSchema?: boolean): NormalizedArguments<S, O>;
export default normalizeArgs;
