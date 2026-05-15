{{/*
Common labels + name helpers for the AEGIS chart.
*/}}

{{- define "aegis.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aegis.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "aegis.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "aegis.apiImage" -}}
{{ printf "%s/%s:%s" .Values.image.registry .Values.image.repository .Values.image.tag }}
{{- end -}}

{{- define "aegis.webImage" -}}
{{ printf "%s/%s:%s" .Values.image.registry .Values.image.webRepository .Values.image.tag }}
{{- end -}}

{{/* envFrom block that pulls every required secret. */}}
{{- define "aegis.envFromSecrets" -}}
- secretRef:
    name: {{ .Values.secrets.database }}
- secretRef:
    name: {{ .Values.secrets.ingest }}
- secretRef:
    name: {{ .Values.secrets.fernet }}
{{- if .Values.secrets.anthropic }}
- secretRef:
    name: {{ .Values.secrets.anthropic }}
    optional: true
{{- end }}
{{- end -}}
