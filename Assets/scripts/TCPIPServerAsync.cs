using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using System;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Collections.Concurrent;

// Simple main thread dispatcher for Unity
public class UnityMainThreadDispatcher : MonoBehaviour
{
    private static UnityMainThreadDispatcher _instance;
    private ConcurrentQueue<Action> _executionQueue = new ConcurrentQueue<Action>();

    void Awake()
    {
        if (_instance == null)
        {
            _instance = this;
            DontDestroyOnLoad(gameObject);
        }
        else if (_instance != this)
        {
            Destroy(gameObject);
        }
    }

    public static UnityMainThreadDispatcher Instance()
    {
        return _instance;
    }

    void Update()
    {
        while (_executionQueue.TryDequeue(out Action action))
        {
            action?.Invoke();
        }
    }

    public void Enqueue(Action action)
    {
        _executionQueue.Enqueue(action);
    }
}

public class TCPIPServerAsync : MonoBehaviour
{
// Use this for initialization

System.Threading.Thread SocketThread;
volatile bool keepReading = false;

// Traffic simulation data structures
[System.Serializable]
public class CarData
{
    public string id;
    public string origin;
    public string original_origin;
    public Vector2 position;
    public Vector2 direction;
    public string state;
    public string turn;
    public bool turned;
    public string target_intersection;
    public int wait_time;
}

[System.Serializable]
public class TimestepData
{
    public int timestep;
    public Dictionary<string, string> traffic_lights;
    public List<CarData> cars;
}

[System.Serializable]
public class TrafficLights
{
    public string main_E;
    public string main_W;
    public string north_center;
    public string south_left;
    public string south_right;
}

// Game objects for visualization
public GameObject[] carPrefabs; // Assign multiple car prefabs in the inspector for randomization
public GameObject trafficLightPrefab; // Assign traffic light prefab in inspector
public Transform intersectionCenter; // Center point of intersection

// Runtime data
private List<TimestepData> movementData = new List<TimestepData>();
private Dictionary<string, GameObject> activeCars = new Dictionary<string, GameObject>();
private Dictionary<string, GameObject> trafficLights = new Dictionary<string, GameObject>();
private int currentTimestep = 0;
private bool isPlaying = false;
private float playbackSpeed = 0.1f; // seconds per timestep (MUCH faster for timelapse effect)

// Smooth movement data
private Dictionary<string, Vector3> targetPositions = new Dictionary<string, Vector3>();
private Dictionary<string, Quaternion> targetRotations = new Dictionary<string, Quaternion>();
private float interpolationSpeed = 15.0f; // How fast cars move between positions (increased for large movements)

void Start()
{
    Application.runInBackground = true;
    
    // Initialize the main thread dispatcher
    if (UnityMainThreadDispatcher.Instance() == null)
    {
        GameObject go = new GameObject("UnityMainThreadDispatcher");
        go.AddComponent<UnityMainThreadDispatcher>();
    }
    
    startServer();
    InitializeTrafficLights();
}

void Update()
{
    // Handle playback of traffic simulation
    if (isPlaying && movementData.Count > 0)
    {
        if (Time.time - lastTimestepTime >= playbackSpeed)
        {
            PlayNextTimestep();
            lastTimestepTime = Time.time;
        }
    }
    
    // Smooth interpolation of car movements
    SmoothCarMovements();
}

private float lastTimestepTime = 0;

void startServer()
{
    SocketThread = new System.Threading.Thread(networkCode);
    SocketThread.IsBackground = true;
    SocketThread.Start();
}



private string getIPAddress()
{
    IPHostEntry host;
    string localIP = "";
    host = Dns.GetHostEntry(Dns.GetHostName());
    foreach (IPAddress ip in host.AddressList)
    {
        if (ip.AddressFamily == AddressFamily.InterNetwork)
        {
            localIP = ip.ToString();
        }

    }
    return localIP;
}


Socket listener;
Socket handler;

void networkCode()
{
    string data;

    // Data buffer for incoming data.
    byte[] bytes = new Byte[1024];

    // host running the application.
    //Create EndPoint
	 IPAddress IPAdr = IPAddress.Parse("127.0.0.1"); // DirecciÃ³n IP
	 IPEndPoint localEndPoint = new IPEndPoint(IPAdr, 1101);

    // Create a TCP/IP socket.
    listener = new Socket(AddressFamily.InterNetwork,SocketType.Stream, ProtocolType.Tcp);

    // Bind the socket to the local endpoint and 
    // listen for incoming connections.

    try
    {
        listener.Bind(localEndPoint);
        listener.Listen(10);

        // Start listening for connections.
        while (true)
        {
            keepReading = true;

            // Program is suspended while waiting for an incoming connection.
            Debug.Log("Waiting for Connection");     //It works

            handler = listener.Accept();
            Debug.Log("Client Connected");     //It doesn't work
            data = null;
				
				byte[] SendBytes = System.Text.Encoding.Default.GetBytes("I will send key");
			   handler.Send(SendBytes); // dar al cliente
			
			

            // An incoming connection needs to be processed.
            while (keepReading)
            {
                bytes = new byte[4096];
                int bytesRec = handler.Receive(bytes);
                
                if (bytesRec <= 0)
                {
                    keepReading = false;
                    handler.Disconnect(true);
                    break;
                }

                data += System.Text.Encoding.ASCII.GetString(bytes, 0, bytesRec);
                Debug.Log("Received from Client: " + data);
                
                if (data.IndexOf("$") > -1)
                {
                    // Check if this is traffic simulation data
                    if (data.Contains("Traffic simulation data ready") || data.Contains("Three T-intersection simulation data ready"))
                    {
                        // Extract JSON data (everything between the acknowledgment and $)
                        string searchString = data.Contains("Three T-intersection simulation data ready") ? 
                            "Three T-intersection simulation data ready" : "Traffic simulation data ready";
                        int jsonStart = data.IndexOf(searchString) + searchString.Length;
                        int jsonEnd = data.IndexOf("$");
                        if (jsonStart < jsonEnd)
                        {
                            string jsonData = data.Substring(jsonStart, jsonEnd - jsonStart).Trim();
                            Debug.Log("Processing traffic simulation JSON data...");
                            
                            // Process the traffic data on the main thread
                            var dispatcher = UnityMainThreadDispatcher.Instance();
                            if (dispatcher != null)
                            {
                                dispatcher.Enqueue(() => {
                                    ProcessTrafficData(jsonData);
                                });
                            }
                            else
                            {
                                Debug.LogError("UnityMainThreadDispatcher not found! Cannot process traffic data.");
                            }
                        }
                    }
                    break;
                }

                System.Threading.Thread.Sleep(1);
            }

            System.Threading.Thread.Sleep(1);
        }
    }
    catch (Exception e)
    {
        Debug.Log(e.ToString());
    }
}

void stopServer()
{
    keepReading = false;

    //stop thread
    if (SocketThread != null)
    {
        SocketThread.Abort();
    }

    if (handler != null && handler.Connected)
    {
        handler.Disconnect(false);
        Debug.Log("Disconnected!");
    }
}

void OnDisable()
{
    stopServer();
}

// New methods for traffic simulation
void InitializeTrafficLights()
{
    // Create traffic light objects for three T-intersections
    // North center, South left, South right intersections
    if (trafficLightPrefab != null && intersectionCenter != null)
    {
        Vector3 center = intersectionCenter.position;
        
        // Traffic lights positioned at stop lines for the SOUTH_RIGHT intersection (50 units from center)
        // All three lights belong to the south_right intersection
        // Position lights at stop lines, not in the middle of the street
        CreateTrafficLight("main_E", new Vector3(center.x + 58.0f, center.y, center.z - 5.0f)); // East stop line at south_right intersection
        CreateTrafficLight("main_W", new Vector3(center.x + 42.0f, center.y, center.z + 5.0f)); // West stop line at south_right intersection
        
        // South right intersection - the only one with traffic lights
        CreateTrafficLight("south_right", new Vector3(center.x + 45.0f, center.y, center.z - 5.0f)); // South stop line at south_right intersection
        
        // Note: north_center and south_left intersections don't have traffic lights
        // They use incoming traffic detection instead
    }
}

void CreateTrafficLight(string direction, Vector3 position)
{
    // Set individual rotation for each direction to face the intersection
    Quaternion rotation = Quaternion.identity;
    switch (direction)
    {
        case "main_E": // East approach - faces west (toward intersection)
            rotation = Quaternion.Euler(0, 270, 0);
            break;
        case "main_W": // West approach - faces east (toward intersection)
            rotation = Quaternion.Euler(0, 90, 0);
            break;
        case "south_right": // South approach - faces north (toward intersection)
            rotation = Quaternion.Euler(0, 180, 0);
            break;
    }
    
    GameObject lightObj = Instantiate(trafficLightPrefab, position, rotation);
    lightObj.name = $"TrafficLight_{direction}";
    trafficLights[direction] = lightObj;
    
    // Set initial red state
    SetTrafficLightColor(direction, "R");
}

void SetTrafficLightColor(string direction, string state)
{
    if (trafficLights.ContainsKey(direction))
    {
        GameObject lightObj = trafficLights[direction];
        Renderer renderer = lightObj.GetComponent<Renderer>();
        if (renderer != null)
        {
            switch (state)
            {
                case "R": renderer.material.color = Color.red; break;
                case "Y": renderer.material.color = Color.yellow; break;
                case "G": renderer.material.color = Color.green; break;
                case "AR": renderer.material.color = Color.black; break;
            }
        }
    }
}

void ProcessTrafficData(string jsonData)
{
    try
    {
        Debug.Log("Processing traffic simulation data...");
        
        // Parse JSON data
        JArray timesteps = JArray.Parse(jsonData);
        movementData.Clear();
        
        int totalCars = 0;
        foreach (JObject timestep in timesteps)
        {
            TimestepData stepData = new TimestepData();
            stepData.timestep = timestep["timestep"].Value<int>();
            
            // Parse traffic lights
            stepData.traffic_lights = new Dictionary<string, string>();
            JObject lights = timestep["traffic_lights"] as JObject;
            foreach (var light in lights)
            {
                stepData.traffic_lights[light.Key] = light.Value.ToString();
            }
            
            // Parse cars
            stepData.cars = new List<CarData>();
            JArray cars = timestep["cars"] as JArray;
            foreach (JObject car in cars)
            {
                CarData carData = new CarData();
                carData.id = car["id"].ToString();
                carData.origin = car["origin"].ToString();
                carData.original_origin = car["original_origin"].ToString();
                carData.position = new Vector2(
                    car["position"]["x"].Value<float>(),
                    car["position"]["y"].Value<float>()
                );
                carData.direction = new Vector2(
                    car["direction"]["x"].Value<float>(),
                    car["direction"]["y"].Value<float>()
                );
                carData.state = car["state"].ToString();
                carData.turn = car["turn"].ToString();
                carData.turned = car["turned"].Value<bool>();
                carData.target_intersection = car["target_intersection"]?.ToString();
                carData.wait_time = car["wait_time"].Value<int>();
                
                stepData.cars.Add(carData);
                totalCars++;
            }
            
            movementData.Add(stepData);
        }
        
        Debug.Log($"Loaded {movementData.Count} timesteps of traffic data with {totalCars} total car instances");
        
        // Start playback
        currentTimestep = 0;
        isPlaying = true;
        lastTimestepTime = Time.time;
        
    }
    catch (Exception e)
    {
        Debug.LogError($"Error processing traffic data: {e.Message}");
    }
}

void PlayNextTimestep()
{
    if (currentTimestep >= movementData.Count)
    {
        // End of simulation
        isPlaying = false;
        Debug.Log("Traffic simulation playback completed");
        return;
    }
    
    TimestepData currentStep = movementData[currentTimestep];
    
    
    // Update traffic lights
    foreach (var light in currentStep.traffic_lights)
    {
        SetTrafficLightColor(light.Key, light.Value);
    }
    
    // Update car positions
    UpdateCars(currentStep.cars);
    
    currentTimestep++;
}

void UpdateCars(List<CarData> cars)
{
    
    // Remove cars that are no longer in the simulation
    List<string> carsToRemove = new List<string>();
    foreach (var kvp in activeCars)
    {
        bool stillExists = cars.Exists(c => c.id == kvp.Key);
        if (!stillExists)
        {
            carsToRemove.Add(kvp.Key);
        }
    }
    
    foreach (string carId in carsToRemove)
    {
        if (activeCars.ContainsKey(carId))
        {
            Destroy(activeCars[carId]);
            activeCars.Remove(carId);
        }
    }
    
    // Update existing cars and create new ones
    foreach (CarData carData in cars)
    {
        if (activeCars.ContainsKey(carData.id))
        {
            // Set target position and rotation for smooth movement
            Vector3 worldPos = ConvertToWorldPosition(carData.position);
            targetPositions[carData.id] = worldPos;
            
            // Convert 2D direction to 3D rotation (Y in simulation = Z in Unity)
            Vector3 direction3D = new Vector3(carData.direction.x, 0, carData.direction.y);
            if (direction3D != Vector3.zero)
            {
                targetRotations[carData.id] = Quaternion.LookRotation(direction3D);
            }
        }
        else
        {
            // Create new car with random prefab
            GameObject selectedPrefab = GetRandomCarPrefab();
            if (selectedPrefab != null)
            {
                Vector3 worldPos = ConvertToWorldPosition(carData.position);
                GameObject carObj = Instantiate(selectedPrefab, worldPos, Quaternion.identity);
                carObj.name = $"Car_{carData.id}";
                
                
                // Set initial rotation
                // Convert 2D direction to 3D rotation (Y in simulation = Z in Unity)
                Vector3 direction3D = new Vector3(carData.direction.x, 0, carData.direction.y);
                if (direction3D != Vector3.zero)
                {
                    carObj.transform.rotation = Quaternion.LookRotation(direction3D);
                }
                
                // Set initial target positions
                targetPositions[carData.id] = worldPos;
                targetRotations[carData.id] = carObj.transform.rotation;
                
                activeCars[carData.id] = carObj;
            }
        }
    }
}

void SmoothCarMovements()
{
    // Smoothly interpolate all cars to their target positions
    foreach (var kvp in activeCars)
    {
        string carId = kvp.Key;
        GameObject carObj = kvp.Value;
        
        if (targetPositions.ContainsKey(carId))
        {
            Vector3 currentPos = carObj.transform.position;
            Vector3 targetPos = targetPositions[carId];
            float distance = Vector3.Distance(currentPos, targetPos);
            
            // If distance is very large (teleporting), snap to target immediately
            if (distance > 100.0f)
            {
                carObj.transform.position = targetPos;
            }
            else
            {
                // Smooth position interpolation with distance-based speed
                float speed = Mathf.Max(interpolationSpeed, distance * 2.0f); // Faster for larger distances
                carObj.transform.position = Vector3.Lerp(currentPos, targetPos, 
                    speed * Time.deltaTime);
            }
            
            // Smooth rotation interpolation
            if (targetRotations.ContainsKey(carId))
            {
                Quaternion targetRot = targetRotations[carId];
                carObj.transform.rotation = Quaternion.Lerp(carObj.transform.rotation, targetRot, 
                    interpolationSpeed * Time.deltaTime);
            }
        }
    }
}

Vector3 ConvertToWorldPosition(Vector2 simPosition)
{
    // Convert simulation coordinates to Unity world coordinates
    // Scale factor: 1 simulation unit = 1 Unity unit
    // Adjust this based on your intersection size
    Vector3 worldPos = new Vector3(simPosition.x, 0, simPosition.y);
    
    if (intersectionCenter != null)
    {
        worldPos += intersectionCenter.position;
    }
    
    // Debug.Log($"ConvertToWorldPosition: sim({simPosition.x}, {simPosition.y}) -> world({worldPos.x}, {worldPos.y}, {worldPos.z})");
    
    return worldPos;
}

GameObject GetRandomCarPrefab()
{
    // If we have multiple car prefabs, randomly select one
    if (carPrefabs != null && carPrefabs.Length > 0)
    {
        int randomIndex = UnityEngine.Random.Range(0, carPrefabs.Length);
        GameObject selectedPrefab = carPrefabs[randomIndex];
        if (selectedPrefab != null)
        {
            return selectedPrefab;
        }
    }
    
    // If no prefabs are assigned, log error
    Debug.LogError("No car prefabs assigned! Please assign car prefabs in the carPrefabs array in the inspector.");
    return null;
}

// Public methods for external control
public void StartPlayback()
{
    if (movementData.Count > 0)
    {
        isPlaying = true;
        currentTimestep = 0;
        lastTimestepTime = Time.time;
    }
}

public void StopPlayback()
{
    isPlaying = false;
}

public void SetPlaybackSpeed(float speed)
{
    playbackSpeed = Mathf.Max(0.1f, speed);
}
}