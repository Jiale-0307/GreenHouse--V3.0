import type { ExcludedPathMatcher, ParserOptions } from "../options.js";
import type $RefParser from "../index.js";
export default function resolveExternalWithMatcher<S extends object, O extends ParserOptions<S>>(parser: $RefParser<S, O>, options: O, excludedPathMatcher: ExcludedPathMatcher): Promise<void>;
