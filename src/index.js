import { Container, getContainer } from "@cloudflare/containers";

export class Clinic extends Container {
  defaultPort = 8000;
  sleepAfter = "15m";
  enableInternet = false;
  envVars = {
    CLINIC_NO_MODEL: "1",
  };
}

export default {
  async fetch(request, env) {
    return getContainer(env.CLINIC, "demo").fetch(request);
  },
};
