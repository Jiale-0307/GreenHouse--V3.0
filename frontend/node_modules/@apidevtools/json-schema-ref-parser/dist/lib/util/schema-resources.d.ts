import type { ParserOptions } from "../options.js";
import type { JSONSchema } from "../index.js";
import type $Refs from "../refs.js";
export declare function getSchemaBasePath(basePath: string, value: unknown, legacyId?: boolean): string;
export declare function usesDynamicIdScope(value: unknown): boolean;
export declare function registerSchemaResources<S extends object = JSONSchema, O extends ParserOptions<S> = ParserOptions<S>>($refs: $Refs<S, O>, basePath: string, value: unknown, pathType?: string | unknown, dynamicIdScope?: boolean): void;
export declare function getSchemaId(value: unknown, inheritedLegacyId?: boolean): string | undefined;
export declare function getSchemaIdMode(value: unknown, inheritedLegacyId?: boolean): boolean;
