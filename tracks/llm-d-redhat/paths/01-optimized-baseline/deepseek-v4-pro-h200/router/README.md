# Router values

`values.yaml` is shared by every arm. Each `arm-<name>.yaml` sets the scheduler
(EndpointPickerConfig), and `rendered-<name>.yaml` is the chart rendered with both files.
Apply one rendered file, then restart `deploy/llmd-epp` so the router reloads its config and
starts with an empty prefix index.
