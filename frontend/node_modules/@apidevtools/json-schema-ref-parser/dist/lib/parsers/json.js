import { ParserError } from "../util/errors.js";
export default {
    /**
     * The order that this parser will run, in relation to other parsers.
     */
    order: 100,
    /**
     * Whether to allow "empty" files. This includes zero-byte files, as well as empty JSON objects.
     */
    allowEmpty: true,
    /**
     * Determines whether this parser can parse a given file reference.
     * Parsers that match will be tried, in order, until one successfully parses the file.
     * Parsers that don't match will be skipped, UNLESS none of the parsers match, in which case
     * every parser will be tried.
     */
    canParse: ".json",
    /**
     * Allow JSON files with byte order marks (BOM)
     */
    allowBOM: true,
    /**
     * Parses the given file as JSON
     */
    async parse(file) {
        let data = file.data;
        if (Buffer.isBuffer(data)) {
            data = data.toString();
        }
        if (typeof data === "string") {
            if (data.trim().length === 0) {
                return; // This mirrors the YAML behavior
            }
            if (this.allowBOM && data.charCodeAt(0) === 0xfeff) {
                data = data.slice(1);
            }
            try {
                return JSON.parse(data);
            }
            catch (e) {
                throw new ParserError(e.message, file.url);
            }
        }
        else {
            // data is already a JavaScript value (object, array, number, null, NaN, etc.)
            return data;
        }
    },
};
