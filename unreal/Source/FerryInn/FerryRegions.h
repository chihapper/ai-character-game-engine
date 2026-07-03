// Named places a mind can want to be — the same affordance vocabulary the Unity client used,
// anchored to REAL coordinates measured from the tavern map (unreal/measure_tavern.py), not
// guessed. Units are UE centimeters, floor z=0.
#pragma once

#include "CoreMinimal.h"

struct FERRYINN_API FerryRegions
{
    /** name -> anchor for /Game/Medieval_Tavern/Map/Demo_level */
    static const TMap<FString, FVector>& All()
    {
        static const TMap<FString, FVector> Regions = {
            { TEXT("the door"),                  FVector(-760.f,  135.f, 0.f) },  // west entrance
            { TEXT("the bar"),                   FVector( 250.f, -240.f, 0.f) },  // patron side of the counter
            { TEXT("behind the bar"),            FVector( 620.f, -240.f, 0.f) },  // barkeep side: counter x~440, shelves x~860
            { TEXT("the long table"),            FVector( -30.f, -540.f, 0.f) },  // central bench rows
            { TEXT("a corner table"),            FVector(-650.f, -350.f, 0.f) },  // west, chairs
            { TEXT("the far tables"),            FVector(-150.f, 1050.f, 0.f) },  // south cluster
            { TEXT("the stairs"),                FVector(-330.f,-1300.f, 0.f) },  // north, up to the rooms
            { TEXT("the middle of the taproom"), FVector( -80.f,  150.f, 0.f) },
        };
        return Regions;
    }

    static FVector Anchor(const FString& Name)
    {
        const FVector* Found = All().Find(Name);
        return Found ? *Found : FVector::ZeroVector;
    }

    /** nearest region to a spot — the world's answer to "where am I?" */
    static FString NameAt(const FVector& Pos)
    {
        FString Best = TEXT("the middle of the taproom");
        float BestDist = TNumericLimits<float>::Max();
        for (const TPair<FString, FVector>& It : All())
        {
            const float D = FVector::Dist2D(Pos, It.Value);
            if (D < BestDist) { BestDist = D; Best = It.Key; }
        }
        return Best;
    }
};
