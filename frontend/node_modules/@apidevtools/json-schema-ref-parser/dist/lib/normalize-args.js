import { getNewOptions } from "./options.js";
/**
 * Normalizes the given arguments, accounting for optional args.
 * Operations that delegate to parse can defer cloning until that call.
 */
export function normalizeArgs(_args, cloneSchema = true) {
    let path;
    let schema;
    let options;
    let callback;
    const args = Array.prototype.slice.call(_args);
    if (typeof args[args.length - 1] === "function") {
        // The last parameter is a callback function
        callback = args.pop();
    }
    if (typeof args[0] === "string") {
        // The first parameter is the path
        path = args[0];
        if (typeof args[2] === "object") {
            // The second parameter is the schema, and the third parameter is the options
            schema = args[1];
            options = args[2];
        }
        else {
            // The second parameter is the options
            schema = undefined;
            options = args[1];
        }
    }
    else {
        // The first parameter is the schema
        path = "";
        schema = args[0];
        options = args[1];
    }
    options = getNewOptions(options);
    if (cloneSchema && !options.mutateInputSchema && typeof schema === "object") {
        // Make a deep clone of the schema, so that we don't alter the original object
        schema = structuredClone(schema);
    }
    return {
        path,
        schema,
        options,
        callback,
    };
}
export default normalizeArgs;
