# Simulación de Tráfico - Intersección Compleja con Unity

Sistema que simula una intersección compleja de tráfico (Av. Ricardo Covarrubias, Blvd. Primavera, Independiente) y la visualiza en tiempo real en Unity usando comunicación TCP/IP.

## Descripción del Sistema

1. **Simulación Python** (`traffic_sim_json.py`) - Ejecuta la simulación de intersección compleja y genera datos de movimiento en JSON
2. **Cliente de Comunicación** (`traffic_client.py`) - Envía datos JSON a Unity vía TCP/IP
3. **Servidor Unity** (`TCPIPServerAsync.cs`) - Recibe datos JSON y los traduce en movimientos de objetos 3D

## Intersección Modelada

### Carreteras:
- **Av. Ricardo Covarrubias**: Carretera principal Este-Oeste
- **Blvd. Primavera**: Ramas izquierda y derecha que se conectan desde el sur
- **Independiente**: Carretera central que se conecta desde el norte

### Direcciones de Tráfico:x
- **main_E**: Tráfico desde el Este en la carretera principal
- **main_W**: Tráfico desde el Oeste en la carretera principal
- **left**: Tráfico desde la rama izquierda de Blvd. Primavera
- **right**: Tráfico desde la rama derecha de Blvd. Primavera
- **center**: Tráfico desde Independiente (norte)

## Requisitos

### Python
```bash
pip install agentpy numpy
```

### Unity
- Instalar el paquete **Newtonsoft.Json** desde Unity Package Manager
- Descargar desde: https://github.com/JamesNK/Newtonsoft.Json

## Configuración de Unity

### 1. Configuración de Escena
1. Crear un GameObject vacío llamado "TrafficController"
2. Adjuntar el script `TCPIPServerAsync` a este GameObject
3. Crear prefabs de autos (cubos simples funcionan bien)
4. Crear prefabs de semáforos (esferas de colores funcionan bien)
5. Crear un GameObject vacío en el centro de la intersección

### 2. Configuración del Inspector
En el componente TCPIPServerAsync, asignar:
- **Car Prefab**: Tu modelo de auto prefab
- **Traffic Light Prefab**: Tu modelo de semáforo prefab
- **Intersection Center**: Transform en el centro de tu intersección

### 3. Configuración de Red
- **IP**: 127.0.0.1 (localhost)
- **Puerto**: 1101
- Asegúrate de que el firewall no bloquee este puerto

## Cómo Ejecutar

### Opción 1: Sistema Completo (Recomendado)
```bash
# 1. Primero iniciar Unity y reproducir la escena
# 2. Luego ejecutar:
python traffic_sim_json.py
```

### Opción 2: Solo Prueba de Conexión
```bash
# Terminal 1 - Servidor de prueba
python server-duplex.py

# Terminal 2 - Cliente de prueba
python client-duplex.py
```

### Opción 3: Prueba del Sistema
```bash
python test_system.py
```

## Parámetros de Simulación

Editar `params` en `traffic_sim_json.py`:
```python
params = {
    'steps': 300,              # Duración de simulación (5 minutos)
    'green_main': 25,          # Tiempo verde para carretera principal
    'green_side': 15,          # Tiempo verde para ramas laterales
    'lambda_main': 0.08,       # Tasa de llegada carretera principal
    'lambda_left': 0.05,       # Tasa de llegada rama izquierda
    'lambda_right': 0.05,      # Tasa de llegada rama derecha
    'lambda_center': 0.04,     # Tasa de llegada Independiente
    'v_free': 8.0,             # Velocidad libre (m/s)
    'policy': 'fixed',         # Política de semáforos (fixed/adaptive)
    'L_main': 60.0,            # Longitud carretera principal
    'L_side': 40.0,            # Longitud ramas laterales
    'intersection_radius': 25.0, # Radio de la intersección
}
```

## Formato de Datos

Los datos JSON contienen pasos de tiempo con:
```json
{
  "timestep": 0,
  "traffic_lights": {
    "main_E": "R", 
    "main_W": "G", 
    "left": "R", 
    "right": "R", 
    "center": "G"
  },
  "cars": [
    {
      "id": "main_E_0_0",
      "origin": "main_E",
      "position": {"x": 60.0, "y": 0.0},
      "direction": {"x": -1, "y": 0},
      "state": "approach",
      "turn": "S",
      "turned": false,
      "wait_time": 0
    }
  ]
}
```

### Estados de Semáforos:
- **R**: Rojo (Red)
- **G**: Verde (Green) 
- **Y**: Amarillo (Yellow)
- **AR**: Todo Rojo (All Red)

### Estados de Vehículos:
- **approach**: Acercándose a la intersección
- **stop**: Detenido en semáforo
- **go**: Moviéndose
- **done**: Completado el recorrido

## Solución de Problemas

### Error "Connection refused"
- Asegúrate de que Unity esté ejecutándose y la escena esté reproduciéndose
- Verifica que el script TCPIPServerAsync esté adjunto y activo

### No aparecen autos en Unity
- Verifica que carPrefab esté asignado en el inspector
- Revisa que intersectionCenter esté configurado correctamente
- Mira la Consola de Unity para mensajes de error

### Los semáforos no cambian
- Verifica que trafficLightPrefab esté asignado
- Asegúrate de que los objetos de semáforo tengan componentes Renderer

### Errores de parsing JSON
- Asegúrate de que Newtonsoft.Json esté instalado en Unity
- Revisa la Consola de Unity para mensajes de error detallados

## Posicionamiento de Semáforos

Los semáforos están posicionados en las líneas de parada según el diagrama:
- **main_E**: (3, 0) - Líneas de parada 7,8,9 (Este)
- **main_W**: (-3, 0) - Líneas de parada 1,2 (Oeste)
- **left**: (-38, 0) - Línea de parada 3 (Rama izquierda)
- **right**: (38, 0) - Línea de parada 6 (Rama derecha)
- **center**: (0, 3) - Línea de parada Independiente (Norte)

## Notas de Rendimiento

- La simulación genera ~300 pasos de tiempo por defecto (5 minutos)
- Cada paso contiene datos de posición para todos los autos activos
- El archivo JSON típicamente es de 1-5 MB dependiendo de la densidad de tráfico
- La reproducción en Unity puede acelerarse reduciendo `playbackSpeed`
- Optimizado para mejor rendimiento con parámetros reducidos

## Archivos del Proyecto

- `traffic_sim_json.py` - Simulación principal de intersección compleja
- `traffic_client.py` - Cliente para enviar datos a Unity
- `test_system.py` - Script de prueba del sistema
- `server-duplex.py` - Servidor de prueba simple
- `client-duplex.py` - Cliente de prueba simple
- `TCPIPServerAsync.cs` - Script de Unity para recibir datos
- `complex_intersection_data.json` - Datos generados por la simulación

## Características de la Intersección

### Movimientos de Giro:
- **Recto (S)**: Continuar en la misma dirección
- **Izquierda (L)**: Girar a la izquierda en la intersección
- **Derecha (R)**: Girar a la derecha en la intersección

### Probabilidades de Giro:
- **Carretera Principal**: 70% recto, 15% izquierda, 15% derecha
- **Rama Izquierda**: 20% recto, 60% izquierda, 20% derecha
- **Rama Derecha**: 20% recto, 20% izquierda, 60% derecha
- **Independiente**: 40% recto, 30% izquierda, 30% derecha
