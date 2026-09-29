// UI language. Spanish lives at /, English at /en; the path prefix is the
// only source of truth so links can be shared per language.
import { createContext, useCallback, useContext } from 'react';

export const LangContext = createContext('es');
export const useLang = () => useContext(LangContext);
export const langFromPath = (pathname) => (pathname === '/en' || pathname.startsWith('/en/') ? 'en' : 'es');
export const basePath = (lang) => (lang === 'en' ? '/en' : '');

// t('key', {var}) → string. Missing English keys fall back to Spanish.
export function useT() {
  const lang = useLang();
  return useCallback((key, vars) => {
    let s = (STRINGS[lang] && STRINGS[lang][key]) ?? STRINGS.es[key] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
    return s;
  }, [lang]);
}

const STRINGS = {
  es: {
    'app.title': 'CDMX Crimen · Transporte',
    'nav.map': 'Mapa',
    'nav.chat': 'Chat',
    'nav.source': 'Carpetas de investigación FGJ CDMX · afluencia STC Metro · datos.cdmx.gob.mx (CC-BY-4.0)',
    'ingest.error': 'Error en la carga de datos: {error}',
    'ingest.bg': 'Actualizando datos en segundo plano: {name}{p}',
    'ingest.first': 'Cargando datos (primer arranque): {name}{p}… el mapa de delitos aparecerá al terminar.',
    'ingest.rows': ' ({n} filas)',
    'ingest.empty': 'Los datos de delitos aún no están cargados. Ejecuta scripts/fetch_data.sh y reinicia el backend.',

    'panel.expand': 'Expandir', 'panel.collapse': 'Colapsar',
    'nodata': 'Sin datos',

    'f.title': 'Filtros',
    'f.period': 'Periodo (fecha del hecho)',
    'f.lastYear': 'Último año', 'f.last12': 'Últimos 12 meses', 'f.all': 'Todo ({a}–{b})',
    'f.category': 'Categoría de delito', 'f.allCats': 'Todas', 'f.highImpact': 'Solo alto impacto',
    'f.less': 'Menos', 'f.showAll': 'Ver las {n}',
    'f.transport': 'Transporte público', 'f.transportOnly': 'Solo delitos contra pasajeros', 'f.cases': '{n} carpetas',
    'f.timeDay': 'Hora y día', 'f.hours': 'Horas', 'f.to': 'a', 'f.hoursNote': '(incl., cruza medianoche)',
    'f.stations': 'Estaciones del Metro', 'f.measure': 'Medida:', 'f.count': 'Conteo',
    'f.rate': 'Por millón de usuarios', 'f.rateTip': 'Carpetas por millón de entradas al Metro en los mismos meses',
    'f.radius': 'Radio:',

    'l.title': 'Capas', 'l.crime': 'Delitos', 'l.basemap': 'Mapa base', 'l.network': 'Red de transporte',
    'l.heat': 'Mapa de calor (hexágonos)', 'l.stations': 'Estaciones del Metro (círculos)',
    'l.colonias': 'Colonias (coropleta)', 'l.alcaldias': 'Alcaldías', 'l.points': 'Carpetas individuales (zoom ≥ 15)',
    'l.sat': 'Satélite (ESRI)',

    'lg.heat': 'Densidad de carpetas (hex {res} m)', 'lg.less': 'menos', 'lg.more': 'más',
    'lg.stRate': 'Estaciones: carpetas por millón de entradas', 'lg.stCount': 'Estaciones: carpetas en el radio',
    'lg.max': 'máx', 'lg.colKm2': 'Colonias: carpetas por km²', 'lg.col': 'Colonias: carpetas',
    'lg.q1': 'quintil 1', 'lg.q5': 'quintil 5', 'lg.points': 'Puntos: carpetas individuales (zoom ≥ 15), color por categoría',

    'p.loading': 'Cargando…', 'p.error': 'Error',
    'p.cases': 'Carpetas', 'p.rankOf': '#{r} de {n}', 'p.perKm2': 'Por km²', 'p.byDensity': '#{r} por densidad',
    'p.perMonth': 'Por mes', 'p.months': '{n} meses', 'p.vsPassengers': 'Contra pasajeros',
    'p.monthly': 'Carpetas por mes', 'p.byCategory': 'Por categoría', 'p.topDelitos': 'Delitos más frecuentes',
    'p.stationsIn': 'Estaciones del Metro en la zona', 'p.alcaldia': 'Alcaldía', 'p.colonia': 'Colonia',
    'p.radius': 'radio {r} m', 'p.perMillion': 'Por millón de entradas', 'p.byRate': '#{r} por tasa',
    'p.noRidership': 'sin afluencia', 'p.dailyEntries': 'Entradas diarias', 'p.average': 'promedio',
    'p.ofTotal': '{p}% del total', 'p.monthlyEntries': 'Carpetas por mes (y entradas al Metro, azul)',
    'p.byMode': 'Delitos contra pasajeros por modo', 'p.hourDow': 'Hora y día del hecho ({p}% con hora válida)',

    'mc.title': '🔎 Pregúntale a los datos',
    'mc.disabled': 'Chat deshabilitado: falta la clave de Gemini o del MCP en secrets/.',
    'mc.otherFilters': 'El asistente usó otros filtros', 'mc.apply': 'Aplicar al mapa',
    'mc.placeholder': '¿Qué estación tiene más robos por usuario?', 'mc.new': 'Nueva pregunta', 'mc.send': 'Enviar',
    'mc.expand': 'Ampliar para leer el reporte', 'mc.shrink': 'Reducir',

    'w.thinking': 'Pensando…', 'w.calling': 'Llamando {tool}…',
    'tool.data_coverage': 'Consultando cobertura…', 'tool.list_categories': 'Listando categorías…',
    'tool.search_station': 'Buscando estación…', 'tool.station_crime_stats': 'Calculando estadísticas de la estación…',
    'tool.rank_stations': 'Ordenando estaciones…', 'tool.crime_trend': 'Calculando tendencia…',
    'tool.category_breakdown': 'Desglosando categorías…', 'tool.time_profile': 'Perfil por hora/día…',
    'tool.area_summary': 'Resumiendo la zona…', 'tool.hotspots': 'Buscando puntos calientes…',
    'tool.compare_periods': 'Comparando periodos…', 'tool.victim_profile': 'Perfil de víctimas…',
    'tool.crime_summary': 'Resumiendo…',

    'c.new': '+ Nueva conversación', 'c.untitled': '(sin título)', 'c.messages': '{n} mensajes',
    'c.confirmDelete': 'Confirmar borrado', 'c.cancel': 'Cancelar', 'c.delete': 'Eliminar',
    'c.empty': 'Sin conversaciones aún.', 'c.showTraceTip': 'Ver razonamiento detallado',
    'c.showTrace': '🧠 Ver razonamiento', 'c.showTraceN': '🧠 Ver razonamiento ({n} {u})',
    'c.placeholder': "Pregunta sobre delitos en la CDMX… ej. '¿qué estación tiene más robos por usuario en 2024?'",
    'c.send': 'Enviar', 'c.onMap': 'Ver en el mapa',
    'c.welcomeTitle': 'Analista de delitos y transporte CDMX',
    'c.welcomeIntro': 'Pregunta sobre patrones en las carpetas de investigación de la FGJ (2019 en adelante) alrededor del Metro, por colonia o alcaldía, por hora, categoría o periodo. Por ejemplo:',
    'c.ex1': '¿Qué estación del Metro tiene más robos por millón de usuarios?',
    'c.ex2': 'Compara el robo a transeúnte en Cuauhtémoc en 2019 vs 2023.',
    'c.ex3': '¿A qué hora y qué día hay más robos cerca de Hidalgo?',
    'c.ex4': '¿Dónde están los puntos calientes de robo de vehículo en Iztapalapa?',
    'c.ex5': '¿Cómo ha cambiado la tendencia de extorsión mes a mes?',
    'c.welcomeNote': 'Los datos son denuncias, no incidencia real; el asistente indica la ventana de fechas y las salvedades en cada respuesta.',
    'c.modelThinking': '🧠 Razonamiento del modelo', 'c.thinkingSuffix': '· pensando…',

    'tr.empty': 'Aún no hay razonamiento que mostrar.', 'tr.waitingNext': 'esperando próxima iteración…',
    'tr.title': '🧠 Razonamiento detallado', 'tr.close': 'Cerrar', 'tr.userQ': '▶ Pregunta del usuario',
    'tr.fallback': 'Razonamiento (sin desglose por iteración)', 'tr.iteration': 'Iteración {n}',
    'tr.tools1': '{n} herramienta', 'tr.toolsN': '{n} herramientas', 'tr.final': 'respuesta final',
    'tr.reason': 'Razonar', 'tr.act': 'Actuar', 'tr.observe': 'Observar', 'tr.answer': 'Responder',
    'tr.waiting': 'esperando…', 'tr.noThinking': '(el modelo no expuso razonamiento en este paso)',
    'tr.noActionsFinal': '(no hay acciones — el modelo respondió directamente)',
    'tr.noActions': '(sin llamadas a herramientas en este paso)', 'tr.noObs': '(sin observaciones)',
    'tr.resultOf': 'resultado de', 'tr.waitingTool': 'esperando respuesta de la herramienta…',
    'tr.less': 'mostrar menos', 'tr.more': 'mostrar {n} líneas más',
  },
  en: {
    'app.title': 'CDMX Crime · Transit',
    'nav.map': 'Map',
    'nav.chat': 'Chat',
    'nav.source': 'FGJ CDMX case files · STC Metro ridership · datos.cdmx.gob.mx (CC-BY-4.0)',
    'ingest.error': 'Data load failed: {error}',
    'ingest.bg': 'Updating data in the background: {name}{p}',
    'ingest.first': 'Loading data (first start): {name}{p}… the crime map will appear when it finishes.',
    'ingest.rows': ' ({n} rows)',
    'ingest.empty': 'Crime data is not loaded yet. Run scripts/fetch_data.sh and restart the backend.',

    'panel.expand': 'Expand', 'panel.collapse': 'Collapse',
    'nodata': 'No data',

    'f.title': 'Filters',
    'f.period': 'Period (date of incident)',
    'f.lastYear': 'Latest year', 'f.last12': 'Last 12 months', 'f.all': 'All ({a}–{b})',
    'f.category': 'Crime category', 'f.allCats': 'All', 'f.highImpact': 'High-impact only',
    'f.less': 'Less', 'f.showAll': 'Show all {n}',
    'f.transport': 'Public transport', 'f.transportOnly': 'Crimes against passengers only', 'f.cases': '{n} cases',
    'f.timeDay': 'Time and day', 'f.hours': 'Hours', 'f.to': 'to', 'f.hoursNote': '(inclusive, wraps midnight)',
    'f.stations': 'Metro stations', 'f.measure': 'Measure:', 'f.count': 'Count',
    'f.rate': 'Per million riders', 'f.rateTip': 'Cases per million Metro entries over the same months',
    'f.radius': 'Radius:',

    'l.title': 'Layers', 'l.crime': 'Crime', 'l.basemap': 'Basemap', 'l.network': 'Transit network',
    'l.heat': 'Heatmap (hexagons)', 'l.stations': 'Metro stations (circles)',
    'l.colonias': 'Colonias (choropleth)', 'l.alcaldias': 'Alcaldías (boroughs)', 'l.points': 'Individual cases (zoom ≥ 15)',
    'l.sat': 'Satellite (ESRI)',

    'lg.heat': 'Case density (hex {res} m)', 'lg.less': 'fewer', 'lg.more': 'more',
    'lg.stRate': 'Stations: cases per million entries', 'lg.stCount': 'Stations: cases within radius',
    'lg.max': 'max', 'lg.colKm2': 'Colonias: cases per km²', 'lg.col': 'Colonias: cases',
    'lg.q1': 'quintile 1', 'lg.q5': 'quintile 5', 'lg.points': 'Points: individual cases (zoom ≥ 15), colored by category',

    'p.loading': 'Loading…', 'p.error': 'Error',
    'p.cases': 'Cases', 'p.rankOf': '#{r} of {n}', 'p.perKm2': 'Per km²', 'p.byDensity': '#{r} by density',
    'p.perMonth': 'Per month', 'p.months': '{n} months', 'p.vsPassengers': 'Against passengers',
    'p.monthly': 'Cases per month', 'p.byCategory': 'By category', 'p.topDelitos': 'Most frequent offences',
    'p.stationsIn': 'Metro stations in the area', 'p.alcaldia': 'Alcaldía (borough)', 'p.colonia': 'Colonia',
    'p.radius': 'radius {r} m', 'p.perMillion': 'Per million entries', 'p.byRate': '#{r} by rate',
    'p.noRidership': 'no ridership data', 'p.dailyEntries': 'Daily entries', 'p.average': 'average',
    'p.ofTotal': '{p}% of total', 'p.monthlyEntries': 'Cases per month (and Metro entries, blue)',
    'p.byMode': 'Crimes against passengers by mode', 'p.hourDow': 'Time and day of incident ({p}% with valid time)',

    'mc.title': '🔎 Ask the data',
    'mc.disabled': 'Chat disabled: the Gemini or MCP key is missing in secrets/.',
    'mc.otherFilters': 'The assistant used different filters', 'mc.apply': 'Apply to map',
    'mc.placeholder': 'Which station has the most robberies per rider?', 'mc.new': 'New question', 'mc.send': 'Send',
    'mc.expand': 'Expand to read the report', 'mc.shrink': 'Shrink',

    'w.thinking': 'Thinking…', 'w.calling': 'Calling {tool}…',
    'tool.data_coverage': 'Checking coverage…', 'tool.list_categories': 'Listing categories…',
    'tool.search_station': 'Finding station…', 'tool.station_crime_stats': 'Computing station statistics…',
    'tool.rank_stations': 'Ranking stations…', 'tool.crime_trend': 'Computing trend…',
    'tool.category_breakdown': 'Breaking down categories…', 'tool.time_profile': 'Hour/day profile…',
    'tool.area_summary': 'Summarizing the area…', 'tool.hotspots': 'Finding hotspots…',
    'tool.compare_periods': 'Comparing periods…', 'tool.victim_profile': 'Victim profile…',
    'tool.crime_summary': 'Summarizing…',

    'c.new': '+ New conversation', 'c.untitled': '(untitled)', 'c.messages': '{n} messages',
    'c.confirmDelete': 'Confirm delete', 'c.cancel': 'Cancel', 'c.delete': 'Delete',
    'c.empty': 'No conversations yet.', 'c.showTraceTip': 'Show detailed reasoning',
    'c.showTrace': '🧠 Show reasoning', 'c.showTraceN': '🧠 Show reasoning ({n} {u})',
    'c.placeholder': "Ask about crime in Mexico City… e.g. 'which station has the most robberies per rider in 2024?'",
    'c.send': 'Send', 'c.onMap': 'Show on map',
    'c.welcomeTitle': 'Mexico City crime and transit analyst',
    'c.welcomeIntro': 'Ask about patterns in the FGJ case files (2019 onward) around the Metro, by colonia or alcaldía, by time of day, category or period. For example:',
    'c.ex1': 'Which Metro station has the most robberies per million riders?',
    'c.ex2': 'Compare street robbery in Cuauhtémoc in 2019 vs 2023.',
    'c.ex3': 'At what time and on which day are there the most robberies near Hidalgo?',
    'c.ex4': 'Where are the vehicle theft hotspots in Iztapalapa?',
    'c.ex5': 'How has the extortion trend changed month by month?',
    'c.welcomeNote': 'The data is reported crime, not true incidence; the assistant states the date window and caveats in every answer.',
    'c.modelThinking': '🧠 Model reasoning', 'c.thinkingSuffix': '· thinking…',

    'tr.empty': 'No reasoning to show yet.', 'tr.waitingNext': 'waiting for next iteration…',
    'tr.title': '🧠 Detailed reasoning', 'tr.close': 'Close', 'tr.userQ': '▶ User question',
    'tr.fallback': 'Reasoning (no per-iteration breakdown)', 'tr.iteration': 'Iteration {n}',
    'tr.tools1': '{n} tool', 'tr.toolsN': '{n} tools', 'tr.final': 'final answer',
    'tr.reason': 'Reason', 'tr.act': 'Act', 'tr.observe': 'Observe', 'tr.answer': 'Answer',
    'tr.waiting': 'waiting…', 'tr.noThinking': '(the model exposed no reasoning in this step)',
    'tr.noActionsFinal': '(no actions — the model answered directly)',
    'tr.noActions': '(no tool calls in this step)', 'tr.noObs': '(no observations)',
    'tr.resultOf': 'result of', 'tr.waitingTool': 'waiting for the tool response…',
    'tr.less': 'show less', 'tr.more': 'show {n} more lines',
  },
};
