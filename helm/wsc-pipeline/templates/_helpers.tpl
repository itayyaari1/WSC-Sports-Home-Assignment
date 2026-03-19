{{/*
Chart name (truncated to 63 chars).
*/}}
{{- define "wsc-pipeline.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully-qualified release name.
When the release name already contains the chart name we don't repeat it.
*/}}
{{- define "wsc-pipeline.fullname" -}}
{{- if contains .Chart.Name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "wsc-pipeline.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "wsc-pipeline.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Kafka bootstrap server URL (internal cluster DNS).
Bitnami Kafka chart exposes the CLIENT listener on <release>-kafka:9092.
*/}}
{{- define "wsc-pipeline.kafkaBootstrap" -}}
{{- printf "%s-kafka:9092" .Release.Name }}
{{- end }}

{{/*
MinIO S3 endpoint URL (internal cluster DNS).
Bitnami MinIO chart exposes the API on <release>-minio:9000.
*/}}
{{- define "wsc-pipeline.minioEndpoint" -}}
{{- printf "http://%s-minio:9000" .Release.Name }}
{{- end }}
