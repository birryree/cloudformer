name        "infra"
description "the 'test-cloud' environment for 'infra'."

override_attributes(
  :leaf => {
    :env => "infra",
    :cloud => "test-cloud"
  }
)
