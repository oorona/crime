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

// English names for the official categories, keyed without accents because
// the source files are inconsistent about them.
const stripAccents = (s) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const CATEGORY_EN = {
  'ROBO A TRANSEUNTE EN VIA PUBLICA CON Y SIN VIOLENCIA': 'Street robbery',
  'ROBO DE VEHICULO CON Y SIN VIOLENCIA': 'Vehicle theft',
  'ROBO A PASAJERO A BORDO DEL METRO CON Y SIN VIOLENCIA': 'Passenger robbery on the Metro',
  'ROBO A PASAJERO A BORDO DE MICROBUS CON Y SIN VIOLENCIA': 'Passenger robbery on microbuses',
  'ROBO A PASAJERO A BORDO DE TAXI CON VIOLENCIA': 'Passenger robbery in taxis (violent)',
  'ROBO A NEGOCIO CON VIOLENCIA': 'Business robbery (violent)',
  'ROBO A CASA HABITACION CON VIOLENCIA': 'Home robbery (violent)',
  'ROBO A REPARTIDOR CON Y SIN VIOLENCIA': 'Delivery worker robbery',
  'ROBO A CUENTAHABIENTE SALIENDO DEL CAJERO CON VIOLENCIA': 'Robbery after ATM withdrawal (violent)',
  'ROBO A TRANSPORTISTA CON Y SIN VIOLENCIA': 'Cargo carrier robbery',
  'HOMICIDIO DOLOSO': 'Intentional homicide',
  'LESIONES DOLOSAS POR DISPARO DE ARMA DE FUEGO': 'Gunshot injuries',
  'VIOLACION': 'Rape',
  'SECUESTRO': 'Kidnapping',
  'DELITO DE BAJO IMPACTO': 'Low-impact crime',
  'HECHO NO DELICTIVO': 'Non-criminal event',
};

// Shorter labels for chips and legends.
export function shortCategory(cat, lang = 'es') {
  if (!cat) return '';
  if (lang === 'en') return CATEGORY_EN[stripAccents(cat)] || cat;
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

const MODE_LABELS_EN = {
  ...MODE_LABELS, MB: 'Metrobús', TROLE: 'Trolleybus', TL: 'Light rail', SUB: 'Suburban rail',
  MICRO: 'Microbus / pesero', TP: 'Public transport',
};
export const modeLabel = (m, lang = 'es') => (lang === 'en' ? MODE_LABELS_EN : MODE_LABELS)[m] || m;

export const DOW_LABELS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const DOW_LABELS_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const dowLabels = (lang = 'es') => (lang === 'en' ? DOW_LABELS_EN : DOW_LABELS);

// Viridis-like ramp used for station circles and the colonia choropleth.
export const SEQ_RAMP = ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'];
