import agentpy as ap
import numpy as np
import json
import socket
import time

# Parameters for three T-intersections: north center, south left, south right
params = {
    'steps': 300,          # duración en ticks (1 tick = 1 s) - reducido para animación
    'green_main': 25,      # VERDE para tráfico principal (carretera horizontal)
    'green_side': 15,      # VERDE para rama vertical (carretera vertical)
    'yellow': 3,           # ÁMBAR
    'all_red': 1,          # ALL-RED (despeje)
    
    # Tasas Poisson de arribo (veh/s) por aproximación - reducidas para animación
    'lambda_main_east': 0.06,   # Main road traffic (Este)
    'lambda_main_west': 0.06,   # Main road traffic (Oeste)
    'lambda_north_center': 0.04,  # Norte al centro
    'lambda_south_left': 0.04,    # Sur izquierda
    'lambda_south_right': 0.04,   # Sur derecha
    
    # Cinemática (ajustada para escala más grande)
    'v_free': 30.0,        # m/s (REDUCIDO para movimiento más suave)
    'headway': 8.0,       # m separación mínima (REDUCIDO para menos saltos) 
    
    # Geometría para tres intersecciones en T (MUCHO MÁS GRANDE para Unity)
    'L_main': 120.0,       # Longitud carretera principal (horizontal) - REDUCIDO
    'L_vertical': 120.0,   # Longitud carretera vertical - MUCHO MÁS GRANDE
    'w': 12.0,              # Ancho de carril (MÁS ANCHO para más separación lateral)
    'intersection_radius': 25.0,   # Radio de cada intersección - MUCHO MÁS GRANDE
    
    # Posiciones de las tres intersecciones (MUCHO MÁS SEPARADAS)
    'intersection_north_x': 0.0,    # Intersección norte (centro)
    'intersection_south_left_x': -40.0,  # Intersección sur izquierda - MOVIDA A LA DERECHA
    'intersection_south_right_x': 50.0,  # Intersección sur derecha - MUCHO MÁS SEPARADA
    
    # Probabilidades de giro para cada origen
    # Main road East - straight west or right to north
    'p_main_east_straight': 0.6,   # Straight to west
    'p_main_east_to_north': 0.4,   # Turn right to north road
    
    # Main road West - straight east or left to south
    'p_main_west_straight': 0.6,   # Straight to east
    'p_main_west_to_south': 0.4,   # Turn left to south roads
    
    # North road - left to west or right to east
    'p_north_left': 0.5,      # Turn left to west
    'p_north_right': 0.5,     # Turn right to east
    
    # South roads - left to west or right to east
    'p_south_left': 0.5,      # Turn left to west
    'p_south_right': 0.5,     # Turn right to east

    # Política: 'adaptive' para control dinámico
    'policy': 'adaptive',

    # Ventanas de verde optimizadas
    'gmin_main': 10, 'gmax_main': 40,
    'gmin_side': 8, 'gmax_side': 25,

    # Umbral de cola
    'theta': 3
}

class ThreeTIntersectionSignals(ap.Agent):
    """Control para tres intersecciones en T: norte centro, sur izquierda, sur derecha"""

    def setup(self, green_main, green_side, yellow, all_red):
        self.g_main, self.g_side = int(green_main), int(green_side)
        self.y, self.ar = int(yellow), int(all_red)
        
        # Solo la intersección derecha tiene semáforos
        self.intersections = {
            'south_right': {'phase': 0, 'sub': 'G', 't_in': 0}  # Solo intersección sur derecha
        }
        
        self.timeline = []      # Timeline for analysis

    def lights(self):
        # Define all directions - only right intersection has lights
        L = {
            'main_E': 'G', 'main_W': 'G',  # Main road - controlled by right intersection
            'north_center': 'G', 'south_left': 'G',  # North and south_left - always green
            'south_right': 'R'  # South right - controlled by right intersection
        }
        
        # Only control the right intersection
        for intersection_id, state in self.intersections.items():
            if intersection_id == 'south_right':
                if state['phase'] == 0:  # Main road green
                    L['main_E'] = L['main_W'] = state['sub']
                    L['south_right'] = 'R'  # South road red
                else:  # Vertical road green
                    L['south_right'] = state['sub']
                    L['main_E'] = L['main_W'] = 'R'  # Main road red
            
        return L

    @property
    def green_dirs(self):
        green_set = set()
        for intersection_id, state in self.intersections.items():
            if state['sub'] != 'G': continue
            if state['phase'] == 0:
                green_set.update(['main_E', 'main_W'])
            else:
                green_set.add(intersection_id)
        return green_set

    def step(self):
        # Log opcional
        self.timeline.append((self.model.t, self.lights()))

        # Control each intersection independently
        for intersection_id, state in self.intersections.items():
            # Atajos de tiempos
            if state['phase'] == 0:    # Main road
                gmin, gmax = self.model.p.gmin_main, self.model.p.gmax_main
            else:                      # Vertical road
                gmin, gmax = self.model.p.gmin_side, self.model.p.gmax_side

            # Política adaptativa durante 'G'
            if state['sub'] == 'G' and getattr(self.model.p, 'policy', 'fixed') == 'adaptive':
                # colas por grupo verde vs. rojo
                qs = self.model.queues_by_dir()
                if state['phase'] == 0:
                    q_green = qs['main_E'] + qs['main_W']
                    q_red = qs.get(intersection_id, 0)
                else:
                    q_green = qs.get(intersection_id, 0)
                    q_red = qs['main_E'] + qs['main_W']

                # Reglas: respetar gmin/gmax; si gmin cumplido, decide extender o cambiar
                if state['t_in'] < gmin:
                    state['t_in'] += 1
                elif state['t_in'] >= gmax:
                    state['sub'], state['t_in'] = 'Y', 0
                elif q_green >= q_red + self.model.p.theta:
                    # Extiende verde
                    state['t_in'] += 1
                else:
                    # Cambia a amarillo
                    state['sub'], state['t_in'] = 'Y', 0
                continue  # importante: no caigas al plan fijo

            # --- Plan fijo ---
            if state['phase'] == 0:  # Main road phase
                if state['sub'] == 'G' and state['t_in'] >= self.g_main: 
                    state['sub'], state['t_in'] = 'Y', 0
                elif state['sub'] == 'Y' and state['t_in'] >= self.y: 
                    state['sub'], state['t_in'] = 'AR', 0
                elif state['sub'] == 'AR' and state['t_in'] >= self.ar: 
                    state['phase'], state['sub'], state['t_in'] = 1, 'G', 0
                else: 
                    state['t_in'] += 1
            else:  # Vertical road phase
                if state['sub'] == 'G' and state['t_in'] >= self.g_side: 
                    state['sub'], state['t_in'] = 'Y', 0
                elif state['sub'] == 'Y' and state['t_in'] >= self.y: 
                    state['sub'], state['t_in'] = 'AR', 0
                elif state['sub'] == 'AR' and state['t_in'] >= self.ar: 
                    state['phase'], state['sub'], state['t_in'] = 0, 'G', 0
                else: 
                    state['t_in'] += 1

class Car(ap.Agent):
    """Vehículo para tres intersecciones en T: norte centro, sur izquierda, sur derecha"""

    def setup(self, origin):
        self.wait = 0           # segundos acumulados detenido
        self.origin = origin    # 'main_E', 'main_W', 'north_center', 'south_left', 'south_right'
        self.original_origin = origin  # Keep track of original origin for coloring
        self.state = 'approach' # 'stop','go','done'
        self.v = self.model.p.v_free
        L_main, L_vertical, w = self.model.p.L_main, self.model.p.L_vertical, self.model.p.w
        R = self.model.p.intersection_radius
        off = w/2

        self.turn = None        # 'L', 'R', or 'S' (for straight)
        self.turned = False     # bandera para no girar más de una vez
        self.car_id = f"{origin}_{self.model.t}_{len(self.model.cars)}"  # Unique ID
        self.target_intersection = None  # Which intersection to use for turns

        # Configuración basada en carriles reales para tres intersecciones en T
        if origin == 'main_E':  # From East on main road
            self.pos = np.array([ +L_main, w/4 ])  # Lado izquierdo del carril (va hacia oeste)
            self.dir = np.array([ -1, 0 ])  # Hacia el oeste
            # Stopline at south_right intersection (where traffic lights are)
            x_south_right = self.model.p.intersection_south_right_x
            self.stopline = np.array([ x_south_right + R/2, 0 ])
            # Desde main road East solo puede ir a norte (der) o continuar recto
            p_straight = getattr(self.model.p, 'p_main_east_straight', 0.6)
            p_to_north = getattr(self.model.p, 'p_main_east_to_north', 0.4)
            choice = np.random.choice(['S', 'R'], p=[p_straight, p_to_north])
            self.turn = choice
            # Goals basados en carriles reales
            if self.turn == 'S':  # Straight to West
                self.goal = np.array([ -L_main, 0 ])
            else:  # Right to north road
                self.target_intersection = 'north'
                x_pos = self.model.p.intersection_north_x
                self.goal = np.array([ x_pos, +L_vertical ])

        elif origin == 'main_W':  # From West on main road
            self.pos = np.array([ -L_main, -w/4 ])  # Lado derecho del carril (va hacia este)
            self.dir = np.array([ +1, 0 ])  # Hacia el este
            # Stopline at south_right intersection (where traffic lights are)
            x_south_right = self.model.p.intersection_south_right_x
            self.stopline = np.array([ x_south_right - R/2, 0 ])
            # Desde main road West solo puede ir a sur o continuar recto
            p_straight = getattr(self.model.p, 'p_main_west_straight', 0.6)
            p_to_south = getattr(self.model.p, 'p_main_west_to_south', 0.4)
            choice = np.random.choice(['S', 'L'], p=[p_straight, p_to_south])
            self.turn = choice
            # Goals basados en carriles reales
            if self.turn == 'S':  # Straight to East
                self.goal = np.array([ +L_main, 0 ])
            else:  # Left to south roads
                # Choose which south intersection to turn at
                self.target_intersection = np.random.choice(['south_left', 'south_right'], p=[0.5, 0.5])
                x_pos = self.model.p[f'intersection_{self.target_intersection}_x']
                # Set stopline at the chosen intersection
                self.stopline = np.array([ x_pos - R/2, 0 ])
                # Goal should be aligned with the south street's left lane (where west cars should go)
                self.goal = np.array([ x_pos - w/4, -L_vertical ])

        elif origin == 'north_center':  # From North on vertical road (centro)
            x_pos = self.model.p.intersection_north_x
            # Desde norte solo puede ir izquierda (oeste) o derecha (este)
            p_left = getattr(self.model.p, 'p_north_left', 0.5)
            p_right = getattr(self.model.p, 'p_north_right', 0.5)
            choice = np.random.choice(['L', 'R'], p=[p_left, p_right])
            self.turn = choice
            
            # Posicionamiento: norte SOLO usa carril izquierdo - el derecho es para tráfico del oeste
            # Todos los autos del norte spawn en el carril izquierdo (x_pos - w/4)
            self.pos = np.array([ x_pos - w/4, +L_vertical + 10 ])  # Solo carril izquierdo
                
            self.dir = np.array([ 0, -1 ])  # Hacia el sur (hacia la calle principal)
            # North cars need to stop for incoming main street traffic
            self.stopline = np.array([ x_pos, +R/2 ])  # Stop before entering main street
            self.target_intersection = 'north'
            
            # Goals basados en carriles reales
            if self.turn == 'L':  # Left turn (oeste)
                self.goal = np.array([ -L_main, 0 ])
            else:  # Right turn (este)
                self.goal = np.array([ +L_main, 0 ])

        elif origin == 'south_left':  # From South on vertical road (izquierda)
            x_pos = self.model.p.intersection_south_left_x
            # Desde sur izquierda solo puede ir izquierda o derecha
            p_left = getattr(self.model.p, 'p_south_left', 0.5)
            p_right = getattr(self.model.p, 'p_south_right', 0.5)
            choice = np.random.choice(['L', 'R'], p=[p_left, p_right])
            self.turn = choice
            
            # Posicionamiento: sur SOLO usa carril derecho - el izquierdo es para tráfico del este
            # Todos los autos del sur spawn en el carril derecho (x_pos + w/4)
            self.pos = np.array([ x_pos + w/4, -L_vertical - 10 ])  # Solo carril derecho
                
            self.dir = np.array([ 0, +1 ])  # Hacia el norte (hacia la calle principal)
            # South_left cars need to stop for incoming main street traffic
            self.stopline = np.array([ x_pos, -R/2 ])  # Stop before entering main street
            self.target_intersection = 'south_left'
            
            # Goals basados en carriles reales - CORREGIDO para seguir carriles correctos
            if self.turn == 'L':  # Left turn (oeste) - va al carril derecho de la calle principal (y > 0)
                self.goal = np.array([ -L_main, w/4 ])  # Carril derecho (top lane)
            else:  # Right turn (este) - va al carril izquierdo de la calle principal (y < 0)
                self.goal = np.array([ +L_main, -w/4 ])  # Carril izquierdo (bottom lane)

        else:  # origin == 'south_right' (From South on vertical road - derecha)
            x_pos = self.model.p.intersection_south_right_x
            # Desde sur derecha solo puede ir izquierda o derecha
            p_left = getattr(self.model.p, 'p_south_left', 0.5)
            p_right = getattr(self.model.p, 'p_south_right', 0.5)
            choice = np.random.choice(['L', 'R'], p=[p_left, p_right])
            self.turn = choice
            
            # Posicionamiento: sur SOLO usa carril derecho - el izquierdo es para tráfico del este
            # Todos los autos del sur spawn en el carril derecho (x_pos + w/4)
            self.pos = np.array([ x_pos + w/4, -L_vertical - 10 ])  # Solo carril derecho
                
            self.dir = np.array([ 0, +1 ])  # Hacia el norte (hacia la calle principal)
            self.stopline = np.array([ x_pos, -R/2 ])  # Much closer to intersection
            self.target_intersection = 'south_right'
            
            # Goals basados en carriles reales - CORREGIDO para seguir carriles correctos
            if self.turn == 'L':  # Left turn (oeste) - va al carril derecho de la calle principal (y > 0)
                self.goal = np.array([ -L_main, w/4 ])  # Carril derecho (top lane)
            else:  # Right turn (este) - va al carril izquierdo de la calle principal (y < 0)
                self.goal = np.array([ +L_main, -w/4 ])  # Carril izquierdo (bottom lane)

    def dist_to(self, p):
        return np.linalg.norm(self.pos - p)
    
    def _check_incoming_main_street_traffic(self):
        """Check if there's incoming traffic on the main street that would conflict with this car's path"""
        # Get intersection position
        if self.origin == 'north_center':
            intersection_x = self.model.p.intersection_north_x
        elif self.origin == 'south_left':
            intersection_x = self.model.p.intersection_south_left_x
        else:
            return False  # Not applicable for other origins
        
        # Check for cars on main street approaching this intersection
        for other_car in self.model.cars:
            if other_car is self or other_car.state == 'done':
                continue
            
            # Check if other car is on main street (y close to 0)
            if abs(other_car.pos[1]) < 2.0:  # On main street
                # Check if other car is approaching this intersection
                if self.origin == 'north_center':
                    # North car turning left/right - check for east/west bound traffic
                    if (other_car.origin == 'main_E' and other_car.pos[0] > intersection_x - 15 and 
                        other_car.pos[0] < intersection_x + 5):  # East bound approaching
                        return True
                    elif (other_car.origin == 'main_W' and other_car.pos[0] < intersection_x + 15 and 
                          other_car.pos[0] > intersection_x - 5):  # West bound approaching
                        return True
                elif self.origin == 'south_left':
                    # South_left car turning left/right - check for east/west bound traffic
                    if (other_car.origin == 'main_E' and other_car.pos[0] > intersection_x - 15 and 
                        other_car.pos[0] < intersection_x + 5):  # East bound approaching
                        return True
                    elif (other_car.origin == 'main_W' and other_car.pos[0] < intersection_x + 15 and 
                          other_car.pos[0] > intersection_x - 5):  # West bound approaching
                        return True
        
        return False

    def step(self):
        if self.state == 'done':
            return

        # Si llegó a la meta, termina
        if self.dist_to(self.goal) < 8.0:
            self.state = 'done'
            return

        # Zona de decisión cerca de la stopline - distancia apropiada para escala grande
        # Cars need larger stopping distance for the big intersection scale
        near = self.dist_to(self.stopline) < 15.0  # Increased for large intersection scale

        # Check if car should stop
        should_stop = False
        
        # Reglas de luz - south_right y main road cars verifican semáforos
        if self.origin in ['south_right', 'main_E', 'main_W']:
            lights = self.model.ctrl.lights()
            light_state = lights.get(self.origin, 'G')
            if near and light_state != 'G':
                should_stop = True
        elif self.origin in ['north_center', 'south_left']:
            # North y south_left cars check for incoming main street traffic
            if near and self._check_incoming_main_street_traffic():
                should_stop = True
        
        if should_stop:
            self.state = 'stop'
            self.wait += 1
            return
        else:
            self.state = 'go'

        # Espacio de seguridad con el líder en el mismo carril - standardized for all cars
        vmax = self.v
        head = self.model.headway_ahead(self)
        if head is not None:
            gap = np.linalg.norm(head.pos - self.pos)
            # Standard headway for all cars - consistent behavior
            if gap < self.model.p.headway * 1.5:  # Same multiplier for all cars
                vmax = 0.0

        # --- Lógica de giro mejorada que respeta carriles para tres intersecciones en T ---
        if not self.turned and self.target_intersection is not None:
            # Check if we're near the target intersection center
            if self.target_intersection == 'north':
                target_x = self.model.p.intersection_north_x
                center_pos = np.array([target_x, 0])
            elif self.target_intersection == 'south_left':
                target_x = self.model.p.intersection_south_left_x
                center_pos = np.array([target_x, 0])
            else:  # south_right
                target_x = self.model.p.intersection_south_right_x
                center_pos = np.array([target_x, 0])
            
            center_dist = np.linalg.norm(self.pos - center_pos)
            
            # Ajustar distancia de giro según el origen y destino
            turn_distance = self.model.p.intersection_radius
            
            if self.origin in ['south_left', 'south_right']:
                # Los autos del sur deben estar muy cerca de y=0 antes de girar
                if abs(self.pos[1]) < 3.0:  # Muy cerca de la calle central
                    turn_distance = 15.0  # Permitir giro desde más lejos
                else:
                    turn_distance = 2.0  # Muy cerca para otros casos
            elif self.origin == 'main_W' and self.turn == 'R':
                # West cars turning right to north - turn closer to intersection
                turn_distance = 2.0  # Más cerca de la intersección
            elif self.origin == 'north_center' and self.turn == 'L':
                # North cars turning left to west - turn closer to intersection but not too close
                turn_distance = 8.0  # Increased for large intersection scale
            elif self.origin == 'north_center' and self.turn == 'R':
                # North cars turning right to east - turn closer to intersection but not too close
                turn_distance = 8.0  # Increased for large intersection scale
            elif self.origin in ['main_E', 'main_W'] and self.turn in ['L', 'R']:
                # Otros autos de main road que van a girar
                turn_distance = 2.0  # Distancia moderada
            
            if center_dist < turn_distance:
                # Perform the turn based on the turn type and intersection
                if self.turn == 'L':  # Left turn
                    if self.origin == 'main_E':  # East to South roads (removed)
                        self.dir = np.array([ 0, -1 ])
                    elif self.origin == 'main_W':  # West to South roads
                        self.dir = np.array([ 0, -1 ])
                        # After left turn from west, position in the south street's left lane
                        # South streets: right lane (x_pos + w/4) for south cars, left lane (x_pos - w/4) for west cars
                        if self.target_intersection == 'south_left':
                            x_pos = self.model.p.intersection_south_left_x
                        else:  # south_right
                            x_pos = self.model.p.intersection_south_right_x
                        self.pos[0] = x_pos - self.model.p.w/4  # Left lane of south street
                    elif self.origin == 'north_center':  # North to West
                        self.dir = np.array([ -1, 0 ])
                        # After left turn from north, position in right lane (top lane, y > 0)
                        self.pos[1] = self.model.p.w/4
                    elif self.origin in ['south_left', 'south_right']:  # South to West
                        self.dir = np.array([ -1, 0 ])
                        # After left turn from south, position in right lane (top lane, y > 0)
                        self.pos[1] = self.model.p.w/4
                        
                elif self.turn == 'R':  # Right turn
                    if self.origin == 'main_E':  # East to North road
                        self.dir = np.array([ 0, +1 ])
                    elif self.origin == 'main_W':  # West to South roads (removed)
                        self.dir = np.array([ 0, -1 ])
                    elif self.origin == 'north_center':  # North to East
                        self.dir = np.array([ +1, 0 ])
                        # After right turn from north, position in left lane (bottom lane, y < 0)
                        self.pos[1] = -self.model.p.w/4
                    elif self.origin in ['south_left', 'south_right']:  # South to East
                        self.dir = np.array([ +1, 0 ])
                        # After right turn from south, position in left lane (bottom lane, y < 0)
                        self.pos[1] = -self.model.p.w/4
                        
                elif self.turn == 'S':  # Straight movement
                    if self.origin == 'south_right':  # South right straight to north
                        self.dir = np.array([ 0, +1 ])  # Continue north
                        
                # For straight movement, direction remains the same
                self.turned = True
                
                # Update origin after turn to maintain correct lane following
                if self.origin == 'main_E' and self.turn == 'L':
                    # Now coming from south
                    if self.target_intersection == 'south_left':
                        self.origin = 'south_left'
                    else:
                        self.origin = 'south_right'
                elif self.origin == 'main_W' and self.turn == 'L':
                    # Now coming from south (west cars turning left to south streets)
                    if self.target_intersection == 'south_left':
                        self.origin = 'south_left'
                    else:
                        self.origin = 'south_right'
                elif self.origin == 'main_W' and self.turn == 'R':
                    # Now coming from north
                    self.origin = 'north_center'
                elif self.origin == 'north_center':
                    # North cars turning into main road
                    if self.turn == 'L':  # Left turn to west
                        self.origin = 'main_W'
                    elif self.turn == 'R':  # Right turn to east
                        self.origin = 'main_E'
        
        # --- Lógica para seguir las calles correctamente ---
        # Solo aplicar restricciones de carril si el auto no está cerca de una intersección
        near_intersection = False
        
        # Verificar si está cerca de alguna intersección
        for intersection_id in ['north', 'south_left', 'south_right']:
            if intersection_id == 'north':
                target_x = self.model.p.intersection_north_x
                center_pos = np.array([target_x, 0])
            elif intersection_id == 'south_left':
                target_x = self.model.p.intersection_south_left_x
                center_pos = np.array([target_x, 0])
            else:  # south_right
                target_x = self.model.p.intersection_south_right_x
                center_pos = np.array([target_x, 0])
            
            if np.linalg.norm(self.pos - center_pos) < self.model.p.intersection_radius + 5:
                near_intersection = True
                break
        
        # Solo aplicar restricciones de carril si NO está cerca de una intersección
        if not near_intersection:
            w = self.model.p.w  # Obtener ancho de carril desde parámetros
            
            # Si el auto está en la calle principal, debe mantenerse en su lado correcto
            if abs(self.pos[1]) < 2.0:  # En la calle principal
                # Cars that have turned from south should maintain their correct lanes
                if self.turned and self.origin in ['south_left', 'south_right']:
                    if self.turn == 'L':  # Left turn from south - should be in right lane (top lane, y > 0)
                        self.pos[1] = w/4
                    elif self.turn == 'R':  # Right turn from south - should be in left lane (bottom lane, y < 0)
                        self.pos[1] = -w/4
                elif self.origin == 'main_E' and self.turn == 'S':
                    # Mantener en lado izquierdo del carril (va hacia oeste)
                    self.pos[1] = w/4
                elif self.origin == 'main_W' and self.turn == 'S':
                    # Mantener en lado derecho del carril (va hacia este)
                    self.pos[1] = -w/4
                elif self.turn in ['L', 'R'] and not self.turned:
                    # Aún no ha llegado a la intersección, mantener en su lado
                    if self.origin == 'main_E':
                        self.pos[1] = w/4  # Lado izquierdo (va hacia oeste)
                    elif self.origin == 'main_W':
                        self.pos[1] = -w/4  # Lado derecho (va hacia este)
            
            # Si el auto está en una calle vertical, debe mantenerse en su lado correcto
            elif self.origin == 'north_center':
                # Norte SOLO usa carril izquierdo - el derecho es para tráfico del oeste
                self.pos[0] = self.model.p.intersection_north_x - w/4
            elif self.origin == 'south_left':
                # Check if this car came from west (should use left lane) or from south (should use right lane)
                if hasattr(self, 'original_origin') and self.original_origin == 'main_W':
                    # West cars turning to south_left use left lane
                    self.pos[0] = self.model.p.intersection_south_left_x - w/4
                else:
                    # South cars use right lane
                    self.pos[0] = self.model.p.intersection_south_left_x + w/4
            elif self.origin == 'south_right':
                # Check if this car came from west (should use left lane) or from south (should use right lane)
                if hasattr(self, 'original_origin') and self.original_origin == 'main_W':
                    # West cars turning to south_right use left lane
                    self.pos[0] = self.model.p.intersection_south_right_x - w/4
                else:
                    # South cars use right lane
                    self.pos[0] = self.model.p.intersection_south_right_x + w/4

        # Avanzar con pasos más pequeños para movimiento más suave
        dt = 0.2  # Paso de tiempo más pequeño (0.2 segundos)
        self.pos = self.pos + self.dir * vmax * dt

class ThreeTIntersectionModel(ap.Model):

    def setup(self):
        p = self.p
        self.ctrl = ThreeTIntersectionSignals(self, p.green_main, p.green_side, p.yellow, p.all_red)
        self.cars = ap.AgentList(self, 0, Car)
        self.spawn_counts = {d:0 for d in ['main_E', 'main_W', 'north_center', 'south_left', 'south_right']}
        # Log para análisis
        self.log = []
        self.t = 0  # reloj simple para corridas sin animación
        self.metrics = {
            'throughput': 0,
            'delay_sum': 0,
            'delay_count': 0,
            'qmax': {'main_E': 0, 'main_W': 0, 'north_center': 0, 'south_left': 0, 'south_right': 0}
        }
        # Store movement data for JSON export
        self.movement_data = []

    def headway_ahead(self, me):
        """Líder en el mismo carril y sentido, si existe - handles both horizontal and vertical roads."""
        # Find cars in the same lane and direction
        same_lane_cars = []
        w = self.p.w
        
        for c in self.cars:
            if c is me or c.state == 'done':
                continue
                
            # Check if car is going in the same direction
            if np.allclose(c.dir, me.dir, atol=0.1):
                # Determine lane distance based on road orientation
                if abs(me.dir[0]) > 0.5:  # Moving horizontally (main street)
                    lane_distance = abs(c.pos[1] - me.pos[1])  # Y-coordinate difference
                else:  # Moving vertically (north/south streets)
                    lane_distance = abs(c.pos[0] - me.pos[0])  # X-coordinate difference
                
                if lane_distance < w/2:  # Within same lane
                    same_lane_cars.append(c)
        
        if not same_lane_cars:
            return None
            
        # Find the closest car ahead in the same direction
        ahead = []
        for c in same_lane_cars:
            v = c.pos - me.pos
            proj = np.dot(v, me.dir)
            if proj > 0:  # ahead
                ahead.append((proj, c))
        
        if not ahead:
            return None
            
        return min(ahead, key=lambda x: x[0])[1]

    def spawn_poisson(self, origin, lam):
        k = np.random.poisson(lam)
        for _ in range(k):
            self.cars.append(Car(self, origin=origin))
            self.spawn_counts[origin]+=1

    def queues_by_dir(self):
        qs = {'main_E': 0, 'main_W': 0, 'north_center': 0, 'south_left': 0, 'south_right': 0}
        for c in self.cars:
            if c.state == 'stop':
                qs[c.origin] += 1
        return qs

    def step(self):
        # 1) arribos - spawn vehicles from all directions
        self.spawn_poisson('main_E', self.p.lambda_main_east)
        self.spawn_poisson('main_W', self.p.lambda_main_west)
        self.spawn_poisson('north_center', self.p.lambda_north_center)
        self.spawn_poisson('south_left', self.p.lambda_south_left)
        self.spawn_poisson('south_right', self.p.lambda_south_right)

        # 2) señales
        self.ctrl.step()

        # 3) autos
        self.cars.step()

        # --- métricas por paso ---
        qs = self.queues_by_dir()
        for d in qs:
            self.metrics['qmax'][d] = max(self.metrics['qmax'][d], qs[d])

        # contabilidad de 'done' y delays asociados
        done = [c for c in self.cars if c.state == 'done']
        self.metrics['throughput'] += len(done)
        for c in done:
            self.metrics['delay_sum'] += c.wait
            self.metrics['delay_count'] += 1

        # Capture movement data for this timestep
        timestep_data = {
            'timestep': self.t,
            'traffic_lights': self.ctrl.lights(),
            'cars': []
        }
        
        for car in self.cars:
            if car.state != 'done':
                car_data = {
                    'id': car.car_id,
                    'origin': car.origin,
                    'original_origin': car.original_origin,
                    'position': {'x': float(car.pos[0]), 'y': float(car.pos[1])},
                    'direction': {'x': float(car.dir[0]), 'y': float(car.dir[1])},
                    'state': car.state,
                    'turn': car.turn,
                    'turned': car.turned,
                    'target_intersection': car.target_intersection,
                    'wait_time': car.wait
                }
                timestep_data['cars'].append(car_data)
        
        self.movement_data.append(timestep_data)

        # 4) limpieza de autos terminados
        self.cars = ap.AgentList(self, [c for c in self.cars if c.state != 'done'], Car)
        self.t += 1

    def get_movement_json(self):
        """Return the movement data as JSON string"""
        return json.dumps(self.movement_data, indent=2)
    
    def get_summary_stats(self):
        """Return summary statistics"""
        avg_delay = self.metrics['delay_sum'] / max(self.metrics['delay_count'], 1)
        return {
            'total_timesteps': self.t,
            'total_cars_processed': self.metrics['throughput'],
            'average_delay': avg_delay,
            'max_queues': self.metrics['qmax'],
            'spawn_counts': self.spawn_counts
        }

def run_simulation_and_export_json():
    """Ejecutar la simulación de tres intersecciones en T y exportar resultados como JSON"""
    print("Iniciando simulación de tres intersecciones en T...")
    print("Norte centro, Sur izquierda, Sur derecha")
    
    # Ejecutar simulación
    model = ThreeTIntersectionModel(params)
    model.run()
    
    print(f"Simulación completada. Generados {len(model.movement_data)} pasos de tiempo")
    print(f"Total de autos procesados: {model.metrics['throughput']}")
    print(f"Colas máximas por dirección: {model.metrics['qmax']}")
    
    # Obtener datos JSON
    json_data = model.get_movement_json()
    summary_stats = model.get_summary_stats()
    
    # Guardar datos en archivo
    print("Guardando datos en archivo...")
    with open('three_t_intersection_data.json', 'w') as f:
        f.write(json_data)
    
    # Guardar estadísticas resumidas
    with open('three_t_intersection_stats.json', 'w') as f:
        json.dump(summary_stats, f, indent=2)
    
    print("Datos guardados en:")
    print("- three_t_intersection_data.json (datos de movimiento)")
    print("- three_t_intersection_stats.json (estadísticas resumidas)")
    
    return json_data, summary_stats

def run_simulation_and_send_to_unity():
    """Ejecutar la simulación de tráfico compleja y enviar resultados a Unity"""
    print("Iniciando simulación de intersección compleja...")
    print("Av. Ricardo Covarrubias, Blvd. Primavera, Independiente")
    
    # Ejecutar simulación
    model = ThreeTIntersectionModel(params)
    model.run()
    
    print(f"Simulación completada. Generados {len(model.movement_data)} pasos de tiempo")
    print(f"Total de autos procesados: {model.metrics['throughput']}")
    print(f"Colas máximas por dirección: {model.metrics['qmax']}")
    
    # Obtener datos JSON
    json_data = model.get_movement_json()
    
    # Enviar a Unity
    try:
        print("Conectando al servidor Unity...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 1101))
        
        # Recibir mensaje inicial de Unity
        from_server = s.recv(4096)
        print("Recibido del servidor Unity:", from_server.decode("ascii"))
        
        # Enviar confirmación
        s.send(b"Three T-intersection simulation data ready")
        
        # Enviar datos JSON
        print("Enviando datos de movimiento a Unity...")
        s.send(json_data.encode('utf-8'))
        
        # Enviar marcador de fin
        s.send(b"$")
        
        print("¡Datos enviados exitosamente!")
        s.close()
        
    except Exception as e:
        print(f"Error conectando a Unity: {e}")
        print("Guardando datos en archivo...")
        with open('three_t_intersection_data.json', 'w') as f:
            f.write(json_data)
        print("Datos guardados en three_t_intersection_data.json")

if __name__ == "__main__":
    # Run simulation and export to JSON files
    run_simulation_and_export_json()
    
    # Uncomment the line below if you want to also send to Unity
    # run_simulation_and_send_to_unity()
