using UnityEngine;
using System.Collections;
using System.Collections.Generic;

public class IntersectionSignalController : MonoBehaviour
{
    [Header("Duraciones (segundos)")]
    public int greenNS = 15;
    public int greenEW = 15;
    public int yellow = 3;
    public int allRed = 1;

    [Header("Grupos de semáforos")]
    public List<TrafficLightHead> nsHeads; // Semáforos para carriles N-S
    public List<TrafficLightHead> ewHeads; // Semáforos para carriles E-O

    void Start()
    {
        StartCoroutine(RunPhases());
    }

    IEnumerator RunPhases()
    {
        while (true)
        {
            // NS verde
            SetGroup(nsHeads, LightColor.Green);
            SetGroup(ewHeads, LightColor.Red);
            yield return new WaitForSeconds(greenNS);

            // NS amarillo
            SetGroup(nsHeads, LightColor.Yellow);
            yield return new WaitForSeconds(yellow);

            // Todo en rojo
            SetGroup(nsHeads, LightColor.Red);
            SetGroup(ewHeads, LightColor.Red);
            yield return new WaitForSeconds(allRed);

            // EW verde
            SetGroup(nsHeads, LightColor.Red);
            SetGroup(ewHeads, LightColor.Green);
            yield return new WaitForSeconds(greenEW);

            // EW amarillo
            SetGroup(ewHeads, LightColor.Yellow);
            yield return new WaitForSeconds(yellow);

            // Todo en rojo
            SetGroup(nsHeads, LightColor.Red);
            SetGroup(ewHeads, LightColor.Red);
            yield return new WaitForSeconds(allRed);
        }
    }

    void SetGroup(List<TrafficLightHead> group, LightColor c)
    {
        foreach (var h in group) h.Show(c);
    }
}
