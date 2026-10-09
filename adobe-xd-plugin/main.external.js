const { entrypoints } = require("uxp");
const plugin = require("./main.js");

if (!entrypoints || typeof entrypoints.setup !== "function") {
  throw new Error("Adobe XD UXP entrypoints.setup is unavailable");
}

entrypoints.setup(plugin);
