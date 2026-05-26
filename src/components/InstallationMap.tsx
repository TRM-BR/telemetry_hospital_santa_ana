import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { cn } from '../lib/cn';
import type { InstallationStatus } from '../types/telemetry';

export interface MapMarker {
  id: string;
  lat: number;
  lng: number;
  label: string;
  status?: InstallationStatus;
}

export interface InstallationMapHandle {
  fitBounds(bounds: L.LatLngBoundsExpression): void;
}

interface InstallationMapProps {
  markers: MapMarker[];
  selectedId?: string;
  onMarkerClick?: (id: string) => void;
  onBackgroundClick?: () => void;
  className?: string;
  mapStyle?: MapStyle;
}

const STATUS_COLORS: Record<InstallationStatus, string> = {
  online:  '#3b82f6',
  offline: '#ef4444',
  alert:   '#f59e0b',
};

type MapStyle = 'minimalist' | 'satellite';

const TILE_URLS: Record<MapStyle, string> = {
  minimalist: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  satellite:  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
};

const TILE_ATTRIBUTIONS: Record<MapStyle, string> = {
  minimalist: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
  satellite:  '&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
};

const DEFAULT_CENTER: L.LatLngExpression = [-23.4395, -46.9173];
const DEFAULT_ZOOM = 15;

const MARKER_RADIUS_DEFAULT = 11;
const MARKER_RADIUS_SELECTED = 16;

export const InstallationMap = forwardRef<InstallationMapHandle, InstallationMapProps>(
  ({ markers, selectedId, onMarkerClick, onBackgroundClick, className, mapStyle = 'minimalist' }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<L.Map | null>(null);
    const markersRef = useRef<Map<string, L.CircleMarker>>(new Map());
    const tileLayerRef = useRef<L.TileLayer | null>(null);
    const onBackgroundClickRef = useRef(onBackgroundClick);
    const onMarkerClickRef = useRef(onMarkerClick);

    onBackgroundClickRef.current = onBackgroundClick;
    onMarkerClickRef.current = onMarkerClick;

    useEffect(() => {
      if (!containerRef.current || mapRef.current) return;
      const map = L.map(containerRef.current, {
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        zoomControl: false,
        attributionControl: false,
      });
      map.on('click', () => onBackgroundClickRef.current?.());
      mapRef.current = map;
      return () => {
        map.remove();
        mapRef.current = null;
      };
    }, []);

    useEffect(() => {
      const map = mapRef.current;
      if (!map) return;

      const markerMap = markersRef.current;
      const newIds = new Set(markers.map((m) => m.id));

      for (const [id, marker] of markerMap) {
        if (!newIds.has(id)) {
          map.removeLayer(marker);
          markerMap.delete(id);
        }
      }

      for (const m of markers) {
        const status = m.status ?? 'online';
        const color = STATUS_COLORS[status];
        const isSelected = selectedId === m.id;
        const radius = isSelected ? MARKER_RADIUS_SELECTED : MARKER_RADIUS_DEFAULT;

        const existing = markerMap.get(m.id);
        if (existing) {
          existing.setLatLng([m.lat, m.lng]);
          existing.setStyle({ fillColor: color, radius });
          existing.setTooltipContent(m.label);
          existing.getElement()?.classList.toggle('selected-leaflet-marker', isSelected);
        } else {
          const marker = L.circleMarker([m.lat, m.lng], {
            radius,
            fillColor: color,
            color: '#ffffff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.9,
          }).addTo(map);

          marker.bindTooltip(m.label, {
            direction: 'top',
            offset: L.point(0, -8),
            className: 'installation-tooltip',
          });

          if (isSelected) {
            marker.getElement()?.classList.add('selected-leaflet-marker');
          }

          marker.on('click', (e) => {
            L.DomEvent.stopPropagation(e);
            onMarkerClickRef.current?.(m.id);
          });

          markerMap.set(m.id, marker);
        }
      }
    }, [markers, selectedId]);

    useEffect(() => {
      const map = mapRef.current;
      if (!map) return;
      const url = TILE_URLS[mapStyle];
      const attr = TILE_ATTRIBUTIONS[mapStyle];
      if (tileLayerRef.current) {
        map.removeLayer(tileLayerRef.current);
      }
      tileLayerRef.current = L.tileLayer(url, { maxZoom: 19, attribution: attr }).addTo(map);
    }, [mapStyle]);

    useImperativeHandle(ref, () => ({
      fitBounds(bounds: L.LatLngBoundsExpression) {
        mapRef.current?.fitBounds(bounds, { padding: [50, 50] });
      },
    }));

    return <div ref={containerRef} className={cn('w-full h-full', className)} />;
  },
);

InstallationMap.displayName = 'InstallationMap';

export default InstallationMap;
