import SwaggerParser from "@apidevtools/swagger-parser";
const path = new URL("../../docs/api/openapi.yaml", import.meta.url).pathname;
const spec = await SwaggerParser.validate(path);
console.log(
  `OpenAPI ${spec.openapi}: ${Object.keys(spec.paths).length} paths validated`,
);
