import { MapContainer, ImageOverlay, Marker, Popup } from 'react-leaflet'
import { CRS, divIcon } from 'leaflet'
import 'leaflet/dist/leaflet.css'

export interface FloorPlanMarker {
  id: string
  position: [number, number]
  label?: string
  variant?: 'known' | 'unknown'
}

interface FloorPlanProps {
  imageUrl: string
  bounds: [[number, number], [number, number]]
  markers?: FloorPlanMarker[]
  height?: string
}

export function FloorPlan({ imageUrl, bounds, markers = [], height = '400px' }: FloorPlanProps) {
  return (
    <div style={{ height }} aria-label="Floor plan">
      <MapContainer
        crs={CRS.Simple}
        bounds={bounds}
        style={{ height: '100%', width: '100%' }}
        zoomControl
        attributionControl={false}
      >
        <ImageOverlay url={imageUrl} bounds={bounds} />
        {markers.map((m) => (
          <Marker
            key={m.id}
            position={m.position}
            icon={divIcon({
              className: '',
              html: `<div style="width:10px;height:10px;border-radius:50%;background:${
                m.variant === 'unknown' ? '#dc2626' : '#2b6cb0'
              };"></div>`,
              iconSize: [10, 10],
              iconAnchor: [5, 5],
            })}
          >
            {m.label && <Popup>{m.label}</Popup>}
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
