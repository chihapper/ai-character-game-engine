#include "MindClient.h"

#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Misc/Base64.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

static TSharedPtr<FJsonObject> ParseJson(const FString& Text)
{
    TSharedPtr<FJsonObject> Obj;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
    FJsonSerializer::Deserialize(Reader, Obj);
    return Obj;
}

void UMindClient::PostJson(const FString& Path, const TSharedPtr<FJsonObject>& Body, FMindJsonReply OnReply)
{
    FString Payload;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Payload);
    FJsonSerializer::Serialize(Body.ToSharedRef(), Writer);

    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
    Req->SetURL(BaseUrl + Path);
    Req->SetVerb(TEXT("POST"));
    Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Req->SetContentAsString(Payload);
    Req->SetTimeout(90.0f);   // minds think; the world must not hang up on them
    Req->OnProcessRequestComplete().BindLambda(
        [OnReply](FHttpRequestPtr, FHttpResponsePtr Resp, bool bOk)
        {
            if (!bOk || !Resp.IsValid() || Resp->GetResponseCode() >= 400)
            {
                UE_LOG(LogTemp, Warning, TEXT("MindClient: request failed (%d)"),
                       Resp.IsValid() ? Resp->GetResponseCode() : -1);
                OnReply.ExecuteIfBound(nullptr);
                return;
            }
            OnReply.ExecuteIfBound(ParseJson(Resp->GetContentAsString()));
        });
    Req->ProcessRequest();
}

void UMindClient::Stt(const TArray<uint8>& WavBytes, FMindJsonReply OnReply)
{
    if (SessionId.IsEmpty())
    {
        OnReply.ExecuteIfBound(nullptr);
        return;
    }
    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
    Req->SetURL(BaseUrl + TEXT("/") + SessionId + TEXT("/stt"));
    Req->SetVerb(TEXT("POST"));
    Req->SetHeader(TEXT("Content-Type"), TEXT("application/octet-stream"));
    Req->SetContent(WavBytes);
    Req->SetTimeout(30.0f);
    Req->OnProcessRequestComplete().BindLambda(
        [OnReply](FHttpRequestPtr, FHttpResponsePtr Resp, bool bOk)
        {
            if (!bOk || !Resp.IsValid() || Resp->GetResponseCode() >= 400)
            {
                OnReply.ExecuteIfBound(nullptr);
                return;
            }
            OnReply.ExecuteIfBound(ParseJson(Resp->GetContentAsString()));
        });
    Req->ProcessRequest();
}

void UMindClient::CreateSession(const FString& Scenario, FMindJsonReply OnReply)
{
    const TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
    Body->SetStringField(TEXT("scenario"), Scenario);
    PostJson(TEXT("/session"),
             Body,
             FMindJsonReply::CreateLambda([this, OnReply](TSharedPtr<FJsonObject> Json)
             {
                 if (Json.IsValid())
                 {
                     SessionId = Json->GetStringField(TEXT("session_id"));
                     UE_LOG(LogTemp, Log, TEXT("MindClient: session %s"), *SessionId);
                 }
                 OnReply.ExecuteIfBound(Json);
             }));
}

void UMindClient::Respond(const FString& Slug, const FString& Line, const FString& Location,
                          const TArray<FString>& Present, const FString& Ambient, FMindJsonReply OnReply)
{
    const TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
    Body->SetStringField(TEXT("line"), Line);

    const TSharedPtr<FJsonObject> Sit = MakeShared<FJsonObject>();
    Sit->SetStringField(TEXT("location"), Location);
    TArray<TSharedPtr<FJsonValue>> P;
    for (const FString& S : Present)
    {
        P.Add(MakeShared<FJsonValueString>(S));
    }
    Sit->SetArrayField(TEXT("present"), P);
    if (!Ambient.IsEmpty())
    {
        Sit->SetStringField(TEXT("ambient"), Ambient);
    }
    Body->SetObjectField(TEXT("situation"), Sit);
    PostJson(FString::Printf(TEXT("/%s/%s/respond"), *SessionId, *Slug), Body, OnReply);
}

void UMindClient::Choose(const FString& Slug, const FString& Situation, const TArray<FString>& Options, FMindJsonReply OnReply)
{
    const TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
    Body->SetStringField(TEXT("situation"), Situation);
    TArray<TSharedPtr<FJsonValue>> Opts;
    for (const FString& O : Options)
    {
        Opts.Add(MakeShared<FJsonValueString>(O));
    }
    Body->SetArrayField(TEXT("options"), Opts);
    PostJson(FString::Printf(TEXT("/%s/%s/choose"), *SessionId, *Slug), Body, OnReply);
}

void UMindClient::Observe(float Clock, float Magnitude, const TArray<TPair<FString, FString>>& SlugObservations, FMindJsonReply OnReply)
{
    const TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
    Body->SetNumberField(TEXT("clock"), Clock);
    Body->SetNumberField(TEXT("magnitude"), Magnitude);
    TArray<TSharedPtr<FJsonValue>> Items;
    for (const TPair<FString, FString>& It : SlugObservations)
    {
        const TSharedPtr<FJsonObject> Item = MakeShared<FJsonObject>();
        Item->SetStringField(TEXT("slug"), It.Key);
        Item->SetStringField(TEXT("observed"), It.Value);
        Items.Add(MakeShared<FJsonValueObject>(Item));
    }
    Body->SetArrayField(TEXT("items"), Items);
    PostJson(FString::Printf(TEXT("/%s/observe"), *SessionId), Body, OnReply);
}

void UMindClient::Acted(const FString& Slug, const FString& Action, const FString& Reason)
{
    const TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
    Body->SetStringField(TEXT("action"), Action);
    Body->SetStringField(TEXT("reason"), Reason);
    PostJson(FString::Printf(TEXT("/%s/%s/acted"), *SessionId, *Slug), Body, FMindJsonReply());
}

void UMindClient::Speak(const FString& Slug, const FString& Text, FMindAudioReply OnReply)
{
    const TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
    Body->SetStringField(TEXT("text"), Text);
    FString Payload;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Payload);
    FJsonSerializer::Serialize(Body.ToSharedRef(), Writer);

    const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
    Req->SetURL(FString::Printf(TEXT("%s/%s/%s/speak"), *BaseUrl, *SessionId, *Slug));
    Req->SetVerb(TEXT("POST"));
    Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Req->SetContentAsString(Payload);
    Req->SetTimeout(90.0f);
    Req->OnProcessRequestComplete().BindLambda(
        [OnReply](FHttpRequestPtr, FHttpResponsePtr Resp, bool bOk)
        {
            if (!bOk || !Resp.IsValid() || Resp->GetResponseCode() >= 400)
            {
                OnReply.ExecuteIfBound(TArray<uint8>(), 0);
                return;
            }
            const int32 Rate = FCString::Atoi(*Resp->GetHeader(TEXT("X-Sample-Rate")));
            OnReply.ExecuteIfBound(Resp->GetContent(), Rate > 0 ? Rate : 24000);
        });
    Req->ProcessRequest();
}

void UMindClient::SpeakAnim(const FString& Slug, const FString& Text,
                            const TArray<TSharedPtr<FJsonValue>>& FaceMarks, FMindSpeakAnimReply OnReply)
{
    const TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
    Body->SetStringField(TEXT("text"), Text);
    if (FaceMarks.Num() > 0)
    {
        Body->SetArrayField(TEXT("emotions"), FaceMarks);   // pass the engine's marks through verbatim
    }
    PostJson(FString::Printf(TEXT("/%s/%s/speak_anim"), *SessionId, *Slug), Body,
        FMindJsonReply::CreateLambda([OnReply](TSharedPtr<FJsonObject> Json)
        {
            if (!Json.IsValid())
            {
                OnReply.ExecuteIfBound(TArray<uint8>(), 0, nullptr);
                return;
            }
            TArray<uint8> Pcm;
            FBase64::Decode(Json->GetStringField(TEXT("pcm_b64")), Pcm);
            const int32 Rate = (int32)Json->GetNumberField(TEXT("rate"));
            const TSharedPtr<FJsonObject>* Anim = nullptr;
            Json->TryGetObjectField(TEXT("anim"), Anim);
            OnReply.ExecuteIfBound(Pcm, Rate > 0 ? Rate : 24000, Anim ? *Anim : nullptr);
        }));
}

void UMindClient::Finish()
{
    if (!SessionId.IsEmpty())
    {
        PostJson(FString::Printf(TEXT("/%s/finish"), *SessionId), MakeShared<FJsonObject>(), FMindJsonReply());
        SessionId.Empty();
    }
}
