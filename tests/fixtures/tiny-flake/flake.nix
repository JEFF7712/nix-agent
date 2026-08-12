{
  description = "nix-agent quoting fixture; no inputs";
  outputs = { self }: {
    nixosConfigurations.fixture = {
      config.networking.hostName = "fixture";
    };
  };
}
