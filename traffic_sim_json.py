import agentpy as ap
import numpy as np
import json
import socket
import time

# Parameters optimized for complex intersection
params = {
    'steps': 300,          # Reduced duration (5 minutes)
    'green_main': 25,      # VERDE para tráfico principal (Av. Ricardo Covarrubias)
    'green_side': 15,      # VERDE para ramas laterales (Blvd. Primavera, Independiente)
    'yellow': 3,           # ÁMBAR
    'all_red': 1,          # ALL-RED (despeje)
    
    # Reduced arrival rates for better performance
    'lambda_main': 0.08,   # Main road traffic (Av. Ricardo Covarrubias)
    'lambda_left': 0.05,   # Left Blvd. Primavera
    'lambda_right': 0.05,  # Right Blvd. Primavera  
    'lambda_center': 0.04, # Independiente
    
    # Cinemática
    'v_free': 8.0,         # m/s (slightly faster)
    'headway': 15.0,       # m separación mínima
    
    # Geometría optimizada para intersección compleja
    'L_main': 60.0,        # Longitud carretera principal
    'L_side': 40.0,        # Longitud ramas laterales
    'w': 3.5,              # Ancho de carril (reduced for performance)
    'intersection_radius': 25.0,  # Radio de la intersección
    
    # Probabilidades de giro para cada origen
    # Main road (Av. Ricardo Covarrubias) - mostly through traffic
    'p_main_straight': 0.7,
    'p_main_left': 0.15,   # Turn to Independiente
    'p_main_right': 0.15,  # Turn to side roads
    
    # Left Blvd. Primavera - mostly left turns
    'p_left_straight': 0.2,
    'p_left_left': 0.6,    # Turn left onto main road
    'p_left_right': 0.2,   # Turn right onto main road
    
    # Right Blvd. Primavera - mostly right turns  
    'p_right_straight': 0.2,
    'p_right_left': 0.2,   # Turn left onto main road
    'p_right_right': 0.6,  # Turn right onto main road
    
    # Independiente - mixed movements
    'p_center_straight': 0.4,
    'p_center_left': 0.3,  # Turn left onto main road
    'p_center_right': 0.3, # Turn right onto main road

    # Política: 'fixed' para mejor rendimiento
    'policy': 'fixed',

    # Ventanas de verde optimizadas
    'gmin_main': 10, 'gmax_main': 40,
    'gmin_side': 8, 'gmax_side': 25,

    # Umbral de cola
    'theta': 3
}

class ComplexIntersectionSignals(ap.Agent):
    """Control para intersección: Av. Ricardo Covarrubias, Blvd. Primavera, Independiente"""

    def setup(self, green_main, green_side, yellow, all_red):
        self.g_main, self.g_side = int(green_main), int(green_side)
        self.y, self.ar = int(yellow), int(all_red)
        self.phase = 0          # 0 = Main road green, 1 = Side roads green
        self.sub = 'G'          # 'G','Y','AR'
        self.t_in = 0
        self.timeline = []      # Timeline for analysis

    def lights(self):
        # Define all directions: main road (E-W), left branch, right branch, center branch
        L = {d:'R' for d in ['main_E', 'main_W', 'left', 'right', 'center']}
        
        if self.phase == 0:  # Main road green
            L['main_E'] = L['main_W'] = self.sub
        else:  # Side roads green
            L['left'] = L['right'] = L['center'] = self.sub
            
        return L

    @property
    def green_dirs(self):
        if self.sub != 'G': return set()
        if self.phase == 0:
            return {'main_E', 'main_W'}
        else:
            return {'left', 'right', 'center'}

    def step(self):
        # Log opcional
        self.timeline.append((self.model.t, self.lights()))

        # Atajos de tiempos
        if self.phase == 0:    # Main road
            gmin, gmax = self.model.p.gmin_main, self.model.p.gmax_main
        else:                  # Side roads
            gmin, gmax = self.model.p.gmin_side, self.model.p.gmax_side

        # Política adaptativa durante 'G'
        if self.sub == 'G' and getattr(self.model.p, 'policy', 'fixed') == 'adaptive':
            # colas por grupo verde vs. rojo
            qs = self.model.queues_by_dir()
            if self.phase == 0:
                q_green = qs['main_E'] + qs['main_W']
                q_red   = qs['left'] + qs['right'] + qs['center']
            else:
                q_green = qs['left'] + qs['right'] + qs['center']
                q_red   = qs['main_E'] + qs['main_W']

            # Reglas: respetar gmin/gmax; si gmin cumplido, decide extender o cambiar
            if self.t_in < gmin:
                self.t_in += 1
            elif self.t_in >= gmax:
                self.sub, self.t_in = 'Y', 0
            elif q_green >= q_red + self.model.p.theta:
                # Extiende verde
                self.t_in += 1
            else:
                # Cambia a amarillo
                self.sub, self.t_in = 'Y', 0
            return  # importante: no caigas al plan fijo

        # --- Plan fijo ---
        if self.phase == 0:  # Main road phase
            if self.sub == 'G' and self.t_in >= self.g_main: 
                self.sub, self.t_in = 'Y', 0
            elif self.sub == 'Y' and self.t_in >= self.y: 
                self.sub, self.t_in = 'AR', 0
            elif self.sub == 'AR' and self.t_in >= self.ar: 
                self.phase, self.sub, self.t_in = 1, 'G', 0
            else: 
                self.t_in += 1
        else:  # Side roads phase
            if self.sub == 'G' and self.t_in >= self.g_side: 
                self.sub, self.t_in = 'Y', 0
            elif self.sub == 'Y' and self.t_in >= self.y: 
                self.sub, self.t_in = 'AR', 0
            elif self.sub == 'AR' and self.t_in >= self.ar: 
                self.phase, self.sub, self.t_in = 0, 'G', 0
            else: 
                self.t_in += 1

class Car(ap.Agent):
    """Vehículo para intersección: Av. Ricardo Covarrubias, Blvd. Primavera, Independiente"""

    def setup(self, origin):
        self.wait = 0           # segundos acumulados detenido
        self.origin = origin    # 'main_E', 'main_W', 'left', 'right', 'center'
        self.state = 'approach' # 'stop','go','done'
        self.v = self.model.p.v_free
        L_main, L_side, w = self.model.p.L_main, self.model.p.L_side, self.model.p.w
        R = self.model.p.intersection_radius
        off = w/2

        self.turn = None        # 'L', 'R', or 'S' (for straight)
        self.turned = False     # bandera para no girar más de una vez
        self.car_id = f"{origin}_{self.model.t}_{len(self.model.cars)}"  # Unique ID

        if origin == 'main_E':  # From East on main road
            self.pos = np.array([ +L_main, 0 ])
            self.dir = np.array([ -1, 0 ])
            self.stopline = np.array([ +R+5, 0 ])
            # Decidir giro basado en probabilidades
            p_straight = getattr(self.model.p, 'p_main_straight', 0.7)
            p_left = getattr(self.model.p, 'p_main_left', 0.15)
            p_right = getattr(self.model.p, 'p_main_right', 0.15)
            choice = np.random.choice(['S', 'L', 'R'], p=[p_straight, p_left, p_right])
            self.turn = choice
            # Goals based on turn
            if self.turn == 'S':  # Straight to West
                self.goal = np.array([ -L_main, 0 ])
            elif self.turn == 'L':  # Left to Independiente
                self.goal = np.array([ 0, +L_side ])
            else:  # Right to side roads
                self.goal = np.array([ 0, -L_side ])

        elif origin == 'main_W':  # From West on main road
            self.pos = np.array([ -L_main, 0 ])
            self.dir = np.array([ +1, 0 ])
            self.stopline = np.array([ -R-5, 0 ])
            # Same probabilities as main_E
            p_straight = getattr(self.model.p, 'p_main_straight', 0.7)
            p_left = getattr(self.model.p, 'p_main_left', 0.15)
            p_right = getattr(self.model.p, 'p_main_right', 0.15)
            choice = np.random.choice(['S', 'L', 'R'], p=[p_straight, p_left, p_right])
            self.turn = choice
            # Goals based on turn
            if self.turn == 'S':  # Straight to East
                self.goal = np.array([ +L_main, 0 ])
            elif self.turn == 'L':  # Left to side roads
                self.goal = np.array([ 0, -L_side ])
            else:  # Right to Independiente
                self.goal = np.array([ 0, +L_side ])

        elif origin == 'left':  # From left Blvd. Primavera
            self.pos = np.array([ -L_side, -L_side ])
            self.dir = np.array([ +1, +1 ]) / np.sqrt(2)  # Diagonal
            self.stopline = np.array([ -R-5, -R-5 ])
            # Mostly left turns
            p_straight = getattr(self.model.p, 'p_left_straight', 0.2)
            p_left = getattr(self.model.p, 'p_left_left', 0.6)
            p_right = getattr(self.model.p, 'p_left_right', 0.2)
            choice = np.random.choice(['S', 'L', 'R'], p=[p_straight, p_left, p_right])
            self.turn = choice
            # Goals based on turn
            if self.turn == 'S':  # Straight to main road
                self.goal = np.array([ +L_main, 0 ])
            elif self.turn == 'L':  # Left turn
                self.goal = np.array([ 0, +L_side ])
            else:  # Right turn
                self.goal = np.array([ 0, -L_side ])

        elif origin == 'right':  # From right Blvd. Primavera
            self.pos = np.array([ +L_side, -L_side ])
            self.dir = np.array([ -1, +1 ]) / np.sqrt(2)  # Diagonal
            self.stopline = np.array([ +R+5, -R-5 ])
            # Mostly right turns
            p_straight = getattr(self.model.p, 'p_right_straight', 0.2)
            p_left = getattr(self.model.p, 'p_right_left', 0.2)
            p_right = getattr(self.model.p, 'p_right_right', 0.6)
            choice = np.random.choice(['S', 'L', 'R'], p=[p_straight, p_left, p_right])
            self.turn = choice
            # Goals based on turn
            if self.turn == 'S':  # Straight to main road
                self.goal = np.array([ -L_main, 0 ])
            elif self.turn == 'L':  # Left turn
                self.goal = np.array([ 0, -L_side ])
            else:  # Right turn
                self.goal = np.array([ 0, +L_side ])

        else:  # origin == 'center' (Independiente)
            self.pos = np.array([ 0, +L_side ])
            self.dir = np.array([ 0, -1 ])
            self.stopline = np.array([ 0, +R+5 ])
            # Mixed movements
            p_straight = getattr(self.model.p, 'p_center_straight', 0.4)
            p_left = getattr(self.model.p, 'p_center_left', 0.3)
            p_right = getattr(self.model.p, 'p_center_right', 0.3)
            choice = np.random.choice(['S', 'L', 'R'], p=[p_straight, p_left, p_right])
            self.turn = choice
            # Goals based on turn
            if self.turn == 'S':  # Straight to main road
                self.goal = np.array([ 0, -L_side ])
            elif self.turn == 'L':  # Left turn
                self.goal = np.array([ -L_main, 0 ])
            else:  # Right turn
                self.goal = np.array([ +L_main, 0 ])

    def dist_to(self, p):
        return np.linalg.norm(self.pos - p)

    def step(self):
        if self.state == 'done':
            return

        # Si llegó a la meta, termina
        if self.dist_to(self.goal) < 8.0:
            self.state = 'done'
            return

        # Zona de decisión cerca de la stopline
        near = self.dist_to(self.stopline) < 15.0

        # Reglas de luz
        lights = self.model.ctrl.lights()
        if near and lights[self.origin] != 'G':
            self.state = 'stop'
            self.wait += 1
            return
        else:
            self.state = 'go'

        # Espacio de seguridad con el líder en el mismo carril
        vmax = self.v
        head = self.model.headway_ahead(self)
        if head is not None:
            gap = np.linalg.norm(head.pos - self.pos)
            if gap < self.model.p.headway:
                vmax = 0.0

        # --- Lógica de giro simplificada para intersección compleja ---
        if not self.turned:
            # Check if we're near the intersection center
            center_dist = np.linalg.norm(self.pos)
            if center_dist < self.model.p.intersection_radius:
                # Perform the turn based on the turn type
                if self.turn == 'L':  # Left turn
                    if self.origin in ['main_E', 'main_W']:
                        # Main road to side road
                        if self.origin == 'main_E':
                            self.dir = np.array([ 0, +1 ])  # Turn to Independiente
                        else:
                            self.dir = np.array([ 0, -1 ])  # Turn to side roads
                    else:
                        # Side road to main road
                        if self.origin == 'left':
                            self.dir = np.array([ 0, +1 ])  # Turn to Independiente
                        elif self.origin == 'right':
                            self.dir = np.array([ 0, -1 ])  # Turn to side roads
                        else:  # center
                            self.dir = np.array([ -1, 0 ])  # Turn to main road West
                            
                elif self.turn == 'R':  # Right turn
                    if self.origin in ['main_E', 'main_W']:
                        # Main road to side road
                        if self.origin == 'main_E':
                            self.dir = np.array([ 0, -1 ])  # Turn to side roads
                        else:
                            self.dir = np.array([ 0, +1 ])  # Turn to Independiente
                    else:
                        # Side road to main road
                        if self.origin == 'left':
                            self.dir = np.array([ 0, -1 ])  # Turn to side roads
                        elif self.origin == 'right':
                            self.dir = np.array([ 0, +1 ])  # Turn to Independiente
                        else:  # center
                            self.dir = np.array([ +1, 0 ])  # Turn to main road East
                            
                # For straight movement, direction remains the same
                self.turned = True

        # Avanzar
        self.pos = self.pos + self.dir * vmax * 1.0  # dt=1 s

class ComplexIntersectionModel(ap.Model):

    def setup(self):
        p = self.p
        self.ctrl = ComplexIntersectionSignals(self, p.green_main, p.green_side, p.yellow, p.all_red)
        self.cars = ap.AgentList(self, 0, Car)
        self.spawn_counts = {d:0 for d in ['main_E', 'main_W', 'left', 'right', 'center']}
        # Log para análisis
        self.log = []
        self.t = 0  # reloj simple para corridas sin animación
        self.metrics = {
            'throughput': 0,
            'delay_sum': 0,
            'delay_count': 0,
            'qmax': {'main_E': 0, 'main_W': 0, 'left': 0, 'right': 0, 'center': 0}
        }
        # Store movement data for JSON export
        self.movement_data = []

    def headway_ahead(self, me):
        """Líder en el mismo carril y sentido, si existe."""
        same = [c for c in self.cars if c is not me and np.allclose(c.dir, me.dir)]
        if not same: return None
        # candidato delante si el vector a él está en dirección de me.dir y más adelante
        ahead = []
        for c in same:
            v = c.pos - me.pos
            proj = np.dot(v, me.dir)
            if proj > 0:  # adelante
                ahead.append((proj, c))
        if not ahead: return None
        return min(ahead, key=lambda x: x[0])[1]

    def spawn_poisson(self, origin, lam):
        k = np.random.poisson(lam)
        for _ in range(k):
            self.cars.append(Car(self, origin=origin))
            self.spawn_counts[origin]+=1

    def queues_by_dir(self):
        qs = {'main_E': 0, 'main_W': 0, 'left': 0, 'right': 0, 'center': 0}
        for c in self.cars:
            if c.state == 'stop':
                qs[c.origin] += 1
        return qs

    def step(self):
        # 1) arribos - spawn vehicles from all directions
        self.spawn_poisson('main_E', self.p.lambda_main)
        self.spawn_poisson('main_W', self.p.lambda_main)
        self.spawn_poisson('left', self.p.lambda_left)
        self.spawn_poisson('right', self.p.lambda_right)
        self.spawn_poisson('center', self.p.lambda_center)

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
                    'position': {'x': float(car.pos[0]), 'y': float(car.pos[1])},
                    'direction': {'x': float(car.dir[0]), 'y': float(car.dir[1])},
                    'state': car.state,
                    'turn': car.turn,
                    'turned': car.turned,
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
    

def run_simulation_and_send_to_unity():
    """Ejecutar la simulación de tráfico compleja y enviar resultados a Unity"""
    print("Iniciando simulación de intersección compleja...")
    print("Av. Ricardo Covarrubias, Blvd. Primavera, Independiente")
    
    # Ejecutar simulación
    model = ComplexIntersectionModel(params)
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
        s.send(b"Complex intersection simulation data ready")
        
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
        with open('complex_intersection_data.json', 'w') as f:
            f.write(json_data)
        print("Datos guardados en complex_intersection_data.json")

if __name__ == "__main__":
    run_simulation_and_send_to_unity()
