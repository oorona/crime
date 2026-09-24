// Display config for the 16 official FGJ `categoria_delito` values plus the
// transport-mode codes derived at ingest. Colors are categorical and picked
// to read on the dark basemap; unknown categories fall back to grey.
export const CATEGORY_COLORS = {
  'ROBO A TRANSEUNTE EN VÍA PÚBLICA CON Y SIN VIOLENCIA': '#f97316',
  'ROBO DE VEHÍCULO CON Y SIN VIOLENCIA':                 '#3b82f6',
  'ROBO A PASAJERO A BORDO DEL METRO CON Y SIN VIOLENCIA': '#ff6600',
  'ROBO A PASAJERO A BORDO DE MICROBUS CON Y SIN VIOLENCIA': '#eab308',
  'ROBO A PASAJERO A BORDO DE TAXI CON VIOLENCIA':        '#a3e635',
  'ROBO A NEGOCIO CON VIOLENCIA':                         '#ec4899',
  'ROBO A CASA HABITACIÓN CON VIOLENCIA':                 '#d946ef',
  'ROBO A REPARTIDOR CON Y SIN VIOLENCIA':                '#14b8a6',
  'ROBO A CUENTAHABIENTE SALIENDO DEL CAJERO CON VIOLENCIA': '#06b6d4',
  'ROBO A TRANSPORTISTA CON Y SIN VIOLENCIA':             '#0ea5e9',
  'HOMICIDIO DOLOSO':                                     '#ef4444',
  'LESIONES DOLOSAS POR DISPARO DE ARMA DE FUEGO':        '#b91c1c',
  'VIOLACIÓN':                                            '#a855f7',
  'SECUESTRO':                                            '#7c3aed',
  'DELITO DE BAJO IMPACTO':                               '#64748b',
  'HECHO NO DELICTIVO':                                   '#475569',
};

export const LOW_IMPACT = 'DELITO DE BAJO IMPACTO';
export const NON_CRIMINAL = 'HECHO NO DELICTIVO';

export function categoryColor(cat) {
  return CATEGORY_COLORS[cat] || '#9ca3af';
}

// Shorter labels for chips and legends.
export function shortCategory(cat) {
  if (!cat) return '';
  return cat
    .replace(' CON Y SIN VIOLENCIA', '')
    .replace(' CON VIOLENCIA', ' (c/viol.)')
    .replace('ROBO A PASAJERO A BORDO DEL ', 'Robo pasajero ')
    .replace('ROBO A PASAJERO A BORDO DE ', 'Robo pasajero ')
    .replace('ROBO A TRANSEUNTE EN VÍA PÚBLICA', 'Robo a transeúnte')
    .replace('ROBO A CUENTAHABIENTE SALIENDO DEL CAJERO', 'Robo a cuentahabiente')
    .replace('LESIONES DOLOSAS POR DISPARO DE ARMA DE FUEGO', 'Lesiones por arma de fuego')
    .replace('DELITO DE BAJO IMPACTO', 'Bajo impacto')
    .replace('HECHO NO DELICTIVO', 'Hecho no delictivo')
    .toLowerCase()
    .replace(/^./, c => c.toUpperCase());
}

export const MODE_LABELS = {
  METRO: 'Metro', MB: 'Metrobús', TROLE: 'Trolebús', TL: 'Tren Ligero', SUB: 'Suburbano',
  RTP: 'RTP', MICRO: 'Microbús / pesero', TAXI: 'Taxi', TP: 'Transporte público',
};

export const DOW_LABELS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

// Viridis-like ramp used for station circles and the colonia choropleth.
export const SEQ_RAMP = ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'];
