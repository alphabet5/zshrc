# Metrics


Some common metrics queries 


## ingress-nginx

heat map

```
sum(increase(nginx_ingress_controller_request_duration_seconds_bucket{ingress!="",controller_pod=~"$controller",controller_class=~"$controller_class",controller_namespace=~"$namespace",ingress=~"$ingress",exported_namespace=~"$exported_namespace"}[2m])) by (le)
```

```json
{
  "id": 89,
  "type": "heatmap",
  "title": "Ingress Request Latency Heatmap (Ingress Namespaces)",
  "description": "",
  "gridPos": {
    "x": 12,
    "y": 24,
    "h": 7,
    "w": 12
  },
  "fieldConfig": {
    "defaults": {
      "custom": {
        "scaleDistribution": {
          "type": "linear"
        },
        "hideFrom": {
          "tooltip": false,
          "viz": false,
          "legend": false
        }
      }
    },
    "overrides": []
  },
  "pluginVersion": "11.5.1",
  "targets": [
    {
      "datasource": {
        "type": "prometheus",
        "uid": "fegcko7j2exogc"
      },
      "exemplar": true,
      "expr": "sum(increase(nginx_ingress_controller_request_duration_seconds_bucket{ingress!=\"\",controller_pod=~\"$controller\",controller_class=~\"$controller_class\",controller_namespace=~\"$namespace\",ingress=~\"$ingress\",exported_namespace=~\"$exported_namespace\"}[2m])) by (le)",
      "format": "heatmap",
      "interval": "",
      "legendFormat": "{{le}}",
      "refId": "A",
      "editorMode": "code",
      "range": true
    }
  ],
  "datasource": {
    "type": "prometheus",
    "uid": "fegcko7j2exogc"
  },
  "options": {
    "calculate": false,
    "yAxis": {
      "axisPlacement": "left",
      "reverse": false,
      "unit": "s"
    },
    "rowsFrame": {
      "layout": "auto"
    },
    "color": {
      "mode": "scheme",
      "fill": "#b4ff00",
      "scale": "exponential",
      "exponent": 0.5,
      "scheme": "Warm",
      "steps": 128,
      "reverse": false
    },
    "cellGap": 2,
    "filterValues": {
      "le": 1e-9
    },
    "tooltip": {
      "mode": "single",
      "yHistogram": true,
      "showColorScale": false
    },
    "legend": {
      "show": true
    },
    "exemplars": {
      "color": "rgba(255,0,255,0.7)"
    },
    "calculation": {},
    "cellValues": {},
    "showValue": "never"
  }
}
```