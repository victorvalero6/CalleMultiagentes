using UnityEngine;

public enum LightColor { Red, Yellow, Green }

public class TrafficLightHead : MonoBehaviour
{
    [Header("Renderers de cada luz")]
    public MeshRenderer redMR;
    public MeshRenderer yellowMR;
    public MeshRenderer greenMR;

    [HideInInspector] public LightColor current; // estado actual

    public void Show(LightColor c)
    {
        current = c;
        SetEmission(redMR,   c == LightColor.Red);
        SetEmission(yellowMR,c == LightColor.Yellow);
        SetEmission(greenMR, c == LightColor.Green);
    }

    void SetEmission(MeshRenderer mr, bool on)
    {
        if (!mr) return;
        var mat = mr.material; // instancia única
        if (on) {
            mat.EnableKeyword("_EMISSION");
            mat.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
        } else {
            mat.DisableKeyword("_EMISSION");
        }
    }
}
