// The seam to the MIND SERVER (game/bridge/mind_api.py on :8001) — the same unchanged engine
// that drove the Unity client and the grid arena. This client owns HTTP + JSON; it composes
// nothing and decides nothing. Percepts are composed by the world; minds live on the server.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Dom/JsonObject.h"
#include "MindClient.generated.h"

DECLARE_DELEGATE_OneParam(FMindJsonReply, TSharedPtr<FJsonObject> /*Json, null on failure*/);
DECLARE_DELEGATE_TwoParams(FMindAudioReply, const TArray<uint8>& /*PCM16*/, int32 /*SampleRate*/);

UCLASS()
class FERRYUNREAL_API UMindClient : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    /** POST /session with the scenario; remembers SessionId for every later call. */
    void CreateSession(const FString& Scenario, FMindJsonReply OnReply);

    /** POST /{sid}/{slug}/respond — a spoken exchange (event + situation -> reply, name_spoken). */
    void Respond(const FString& Slug, const FString& Event, const FString& Situation, FMindJsonReply OnReply);

    /** POST /{sid}/{slug}/choose — grounded action pick from afforded options. */
    void Choose(const FString& Slug, const FString& Situation, const TArray<FString>& Options, FMindJsonReply OnReply);

    /** POST /{sid}/observe — the react recipe over real witnesses. */
    void Observe(float Clock, float Magnitude, const TArray<TPair<FString, FString>>& SlugObservations, FMindJsonReply OnReply);

    /** POST /{sid}/{slug}/acted — the mind must KNOW the body did it (anti-confabulation). */
    void Acted(const FString& Slug, const FString& Action, const FString& Reason);

    /** POST /{sid}/{slug}/speak — text -> PCM16 + sample rate (X-Sample-Rate header). */
    void Speak(const FString& Slug, const FString& Text, FMindAudioReply OnReply);

    /** POST /{sid}/finish — close out the night. */
    void Finish();

    bool HasSession() const { return !SessionId.IsEmpty(); }
    FString GetSessionId() const { return SessionId; }

private:
    void PostJson(const FString& Path, const TSharedPtr<FJsonObject>& Body, FMindJsonReply OnReply);

    FString BaseUrl = TEXT("http://127.0.0.1:8001/api/mind");
    FString SessionId;
};
