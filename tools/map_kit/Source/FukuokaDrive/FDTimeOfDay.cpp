#include "FDTimeOfDay.h"
#include "FDCourseInfo.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/Engine.h"
#include "Engine/LocalPlayer.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FDInstances.h"
#include "FDMenu.h"
#include "FDNightLights.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Misc/DateTime.h"

namespace
{
	constexpr int32 DebugMessageKey = 7102;
	// 太陽がこれより沈んだら太陽の光を消す (空の明るさはほぼ残らない。影の計算を省く)
	constexpr float SunOffBelowDeg = -12.f;
	// 霧の一定の色 (エンジン既定の値)。昼の露出 (EV100 15) のときにこの明るさになるよう、露出に合わせて変える
	const FLinearColor DefaultFogColor(0.447f, 0.638f, 1.0f);
	constexpr float FogReferenceEV = 15.f;

	FFDLookKey MakeKey(float Elevation, float EV, const FLinearColor& FogTint, const FLinearColor& SunGlow,
	                   float ForwardScatter, float Bloom, float Saturation, const FLinearColor& Gain)
	{
		FFDLookKey Key;
		Key.SunElevationDeg = Elevation;
		Key.ExposureEV100 = EV;
		Key.FogTint = FogTint;
		Key.SunGlow = SunGlow;
		Key.FogForwardScatter = ForwardScatter;
		Key.BloomIntensity = Bloom;
		Key.Saturation = Saturation;
		Key.ColorGain = Gain;
		return Key;
	}

	FString FormatHour(float Hour)
	{
		const int32 Minutes = FMath::FloorToInt(FMath::Fmod(Hour, 24.f) * 60.f);
		return FString::Printf(TEXT("%02d:%02d"), Minutes / 60, Minutes % 60);
	}
}

AFDTimeOfDay::AFDTimeOfDay()
{
	PrimaryActorTick.bCanEverTick = true;

	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));

	// 月。大気の2番目の光源にすると、空が月明かりでほのかに色づき、月の円盤も描かれる
	MoonLight = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("MoonLight"));
	MoonLight->SetupAttachment(GetRootComponent());
	MoonLight->SetMobility(EComponentMobility::Movable);
	MoonLight->bAtmosphereSunLight = true;
	MoonLight->AtmosphereSunLightIndex = 1;
	MoonLight->Intensity = 0.f;
	MoonLight->LightColor = FColor(217, 230, 255);
	// 月明かりの雲は灰白色に光って夜空が明るく見えるので、雲を照らす分だけ弱める (地面を照らす明るさはそのまま)
	MoonLight->CloudScatteredLuminanceScale = FLinearColor(0.25f, 0.25f, 0.25f);

	// 太陽の高度ごとの見た目。夕景 (高度 0-8°) は露出を抑え、太陽まわりの白い光を弱めて橙を残す
	const FLinearColor White = FLinearColor::White;
	Looks = {
		// 夜 (月明かり)。少し青く、色を薄く (暗い所では色が見えにくい)。
		// 露出を明るくしすぎると夕方のように見え、防犯灯やヘッドライトが目立たない
		MakeKey(-18.f, 1.3f, FLinearColor(0.3f, 0.4f, 0.7f), FLinearColor::Black,
		        0.2f, 0.9f, 0.75f, FLinearColor(0.86f, 0.93f, 1.10f)),
		// 天文薄明の終わりごろ。夜の露出へなめらかにつなぐ
		MakeKey(-13.f, 2.4f, FLinearColor(0.35f, 0.45f, 0.8f), FLinearColor(0.005f, 0.008f, 0.02f),
		        0.22f, 0.85f, 0.85f, FLinearColor(0.9f, 0.95f, 1.07f)),
		// 薄明 (深い青)。露出を上げすぎると夕暮れ後の空と海が白っぽく飛ぶ
		MakeKey(-9.f, 3.0f, FLinearColor(0.4f, 0.5f, 0.9f), FLinearColor(0.01f, 0.015f, 0.04f),
		        0.25f, 0.8f, 0.9f, FLinearColor(0.93f, 0.96f, 1.05f)),
		// 市民薄明の終わり。地面がまだ見えるよう、空の明るさの割に露出を上げる
		MakeKey(-6.f, 6.0f, FLinearColor(0.42f, 0.46f, 0.75f), FLinearColor(0.05f, 0.03f, 0.03f),
		        0.25f, 0.7f, 0.97f, FLinearColor(0.96f, 0.98f, 1.03f)),
		// ブルーアワー (日の入り直後・日の出直前)
		MakeKey(-3.f, 9.5f, FLinearColor(0.45f, 0.42f, 0.6f), FLinearColor(0.12f, 0.055f, 0.025f),
		        0.25f, 0.6f, 1.05f, White),
		// 日の入り・日の出
		MakeKey(2.f, 11.3f, FLinearColor(0.6f, 0.4f, 0.3f), FLinearColor(0.45f, 0.18f, 0.06f),
		        0.25f, 0.45f, 1.15f, FLinearColor(1.04f, 1.0f, 0.94f)),
		// ゴールデンアワー
		MakeKey(8.f, 12.8f, FLinearColor(0.8f, 0.7f, 0.6f), FLinearColor(0.3f, 0.17f, 0.08f),
		        0.35f, 0.5f, 1.1f, FLinearColor(1.02f, 1.0f, 0.97f)),
		// 昼
		MakeKey(25.f, 14.3f, White, FLinearColor(0.12f, 0.11f, 0.09f), 0.5f, 0.5f, 1.0f, White),
		MakeKey(60.f, 15.0f, White, FLinearColor(0.1f, 0.1f, 0.09f), 0.5f, 0.5f, 1.0f, White),
	};
}

void AFDTimeOfDay::BeginPlay()
{
	Super::BeginPlay();
	if (const AFDCourseInfo* Course = AFDCourseInfo::Find(GetWorld()))
	{
		Latitude = Course->Latitude;
		Longitude = Course->Longitude;
		GridRotationDeg = Course->GridRotationDeg;
	}

	FindSceneActors();
	if (StartHour >= 0.f)
	{
		Hour = StartHour;
	}
	CreateInput();
	ApplySeason();
	Apply();
}

// ---------------------------------------------------------------- シーン

void AFDTimeOfDay::FindSceneActors()
{
	UWorld* World = GetWorld();
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!SunLight && Actor->GetClass()->GetName().Contains(TEXT("SunSky")))
		{
			SunLight = Actor->FindComponentByClass<UDirectionalLightComponent>();
			// 開始時刻は SunSky の SolarTime に合わせる (BP の変数なので名前で読む。float でも double でもよい)
			if (const FNumericProperty* Prop = FindFProperty<FNumericProperty>(Actor->GetClass(), TEXT("SolarTime"));
			    Prop && Prop->IsFloatingPoint())
			{
				Hour = static_cast<float>(Prop->GetFloatingPointPropertyValue(Prop->ContainerPtrToValuePtr<void>(Actor)));
			}
		}
		if (!Fog)
		{
			Fog = Actor->FindComponentByClass<UExponentialHeightFogComponent>();
			if (Fog)
			{
				BaseFogDensity = Fog->FogDensity;
			}
		}
		if (APostProcessVolume* Volume = Cast<APostProcessVolume>(Actor); Volume && Volume->bUnbound && !PostProcess)
		{
			PostProcess = Volume;
		}
		if (AFDNightLights* Lights = Cast<AFDNightLights>(Actor))
		{
			NightLights.Add(Lights);
		}
		if (AFDInstances* Seasonal = Cast<AFDInstances>(Actor); Seasonal && Seasonal->SeasonMask != 0)
		{
			SeasonalInstances.Add(Seasonal);
		}
	}

	NightCollection = NightParameters.LoadSynchronous();
	if (!NightCollection)
	{
		UE_LOG(LogTemp, Warning, TEXT("FDTimeOfDay: %s が見つかりません。星空は回らず、防犯灯の光る面は光りません"),
		       *NightParameters.ToString());
	}

	if (!SunLight)
	{
		UE_LOG(LogTemp, Warning, TEXT("FDTimeOfDay: SunSky が見つかりません。太陽は動きません"));
	}
	else if (SunLight->Mobility != EComponentMobility::Movable)
	{
		SunLight->SetMobility(EComponentMobility::Movable);
	}
	if (!PostProcess)
	{
		UE_LOG(LogTemp, Warning, TEXT("FDTimeOfDay: 境界なしの PostProcessVolume が見つかりません。露出は変わりません"));
	}
}

// ---------------------------------------------------------------- 入力

void AFDTimeOfDay::CreateInput()
{
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (!PC)
	{
		return;
	}

	// 入力アセットはコードで作る (FDBikePawn と同じ)
	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_TimeOfDay"));
	ScrubAction = NewObject<UInputAction>(this, TEXT("IA_TimeScrub"));
	ScrubAction->ValueType = EInputActionValueType::Axis1D;
	MappingContext->MapKey(ScrubAction, EKeys::T);
	MappingContext->MapKey(ScrubAction, EKeys::Gamepad_DPad_Right);
	for (const FKey& Key : {EKeys::G, EKeys::Gamepad_DPad_Left})
	{
		FEnhancedActionKeyMapping& Mapping = MappingContext->MapKey(ScrubAction, Key);
		Mapping.Modifiers.Add(NewObject<UInputModifierNegate>(MappingContext));
	}

	const FKey PresetKeys[] = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four};
	PresetActions.Reset();
	for (int32 i = 0; i < static_cast<int32>(UE_ARRAY_COUNT(PresetKeys)); ++i)
	{
		UInputAction* Action = NewObject<UInputAction>(this, *FString::Printf(TEXT("IA_TimePreset%d"), i + 1));
		Action->ValueType = EInputActionValueType::Boolean;
		MappingContext->MapKey(Action, PresetKeys[i]);
		PresetActions.Add(Action);
	}

	SeasonAction = NewObject<UInputAction>(this, TEXT("IA_Season"));
	SeasonAction->ValueType = EInputActionValueType::Boolean;
	MappingContext->MapKey(SeasonAction, EKeys::Y);

	if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
			ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
	{
		Subsystem->AddMappingContext(MappingContext, 1);
	}

	// DefaultInput.ini で EnhancedInputComponent が既定なので、EnableInput で作られる部品もそれになる
	EnableInput(PC);
	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(InputComponent);
	if (!Input)
	{
		UE_LOG(LogTemp, Error, TEXT("FDTimeOfDay: Enhanced Input が有効になっていません"));
		return;
	}
	Input->BindActionValueLambda(ScrubAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V) { ScrubInput = V.Get<float>(); });
	Input->BindActionValueLambda(ScrubAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { ScrubInput = 0.f; });
	for (int32 i = 0; i < PresetActions.Num(); ++i)
	{
		Input->BindActionValueLambda(PresetActions[i], ETriggerEvent::Started, [this, i](const FInputActionValue&)
		{
			GoToHour(PresetHour(i));
		});
	}
	Input->BindActionValueLambda(SeasonAction, ETriggerEvent::Started, [this](const FInputActionValue&) { NextSeason(); });
}

float AFDTimeOfDay::PresetHour(int32 Index) const
{
	float Sunrise = 5.f;
	float Sunset = 19.f;
	ComputeSunriseSunset(Sunrise, Sunset);
	switch (Index)
	{
	case 0:  return Sunrise + MorningAfterSunriseHours;
	case 1:  return NoonHour;
	case 2:  return Sunset - SunsetBeforeSunsetHours;
	default: return Sunset + NightAfterSunsetHours;
	}
}

void AFDTimeOfDay::NextSeason()
{
	if (SeasonDates.IsEmpty())
	{
		return;
	}
	// いまの日付の次へ (一覧にない日付なら最初へ)
	const int32 Current = SeasonDates.IndexOfByKey(FIntPoint(Month, Day));
	const FIntPoint Next = SeasonDates[(Current + 1) % SeasonDates.Num()];
	Month = Next.X;
	Day = Next.Y;
	ApplySeason();
	Apply();
}

void AFDTimeOfDay::ApplySeason()
{
	for (AFDInstances* Seasonal : SeasonalInstances)
	{
		if (Seasonal)
		{
			Seasonal->ApplySeason(Month);
		}
	}
}

// ---------------------------------------------------------------- 時刻

void AFDTimeOfDay::SetHour(float NewHour)
{
	Hour = FMath::Fmod(NewHour, 24.f);
	if (Hour < 0.f)
	{
		Hour += 24.f;
	}
	Apply();
}

void AFDTimeOfDay::GoToHour(float TargetHour)
{
	// いつも時間を先へ進める (夜 → 朝なら夜明けを通る)
	float Delta = FMath::Fmod(TargetHour - Hour, 24.f);
	if (Delta < 0.f)
	{
		Delta += 24.f;
	}
	if (Delta < 1.f / 60.f)
	{
		return;
	}
	bTransitioning = true;
	TransitionRemainingHours = Delta;
	TransitionRateHoursPerSecond = Delta / FMath::Max(TransitionSeconds, 0.1f);
}

void AFDTimeOfDay::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	float Advance = TimeScale * DeltaSeconds / 3600.f;
	if (FMath::Abs(ScrubInput) > 0.01f)
	{
		bTransitioning = false;  // 手で動かしたら 1-4 キーの移動はやめる
		Advance += ScrubInput * ScrubHoursPerSecond * DeltaSeconds;
	}
	else if (bTransitioning)
	{
		const float Step = FMath::Min(TransitionRateHoursPerSecond * DeltaSeconds, TransitionRemainingHours);
		Advance += Step;
		TransitionRemainingHours -= Step;
		bTransitioning = TransitionRemainingHours > 0.f;
	}
	if (Advance != 0.f)
	{
		SetHour(Hour + Advance);
	}

	if (bShowDebugText && FFDSettings::ShowHelpText() && GEngine)
	{
		GEngine->AddOnScreenDebugMessage(
			DebugMessageKey, 0.f, FColor::White,
			FString::Printf(TEXT("%d/%d %s   sun %+5.1f deg   [T/G = time, 1-4 = morning/noon/sunset/night, Y = season, Tab = menu]"),
			                Month, Day, *FormatHour(Hour), SunElevationDeg));
	}
}

void AFDTimeOfDay::ComputeSun(float InHour, float& OutAzimuthDeg, float& OutElevationDeg) const
{
	// NOAA の簡易式 (誤差 0.5° 程度)。夏至 19:12 で方位 296°、高度 3° (SunSky と同じ)
	const int32 DayOfYear = FDateTime(2026, FMath::Clamp(Month, 1, 12),
	                                  FMath::Clamp(Day, 1, FDateTime::DaysInMonth(2026, FMath::Clamp(Month, 1, 12)))).GetDayOfYear();
	const double G = 2.0 * PI / 365.0 * (DayOfYear - 1 + (InHour - 12.0) / 24.0);
	const double EqTimeMin = 229.18 * (0.000075 + 0.001868 * FMath::Cos(G) - 0.032077 * FMath::Sin(G)
	                                   - 0.014615 * FMath::Cos(2 * G) - 0.040849 * FMath::Sin(2 * G));
	const double Decl = 0.006918 - 0.399912 * FMath::Cos(G) + 0.070257 * FMath::Sin(G) - 0.006758 * FMath::Cos(2 * G)
	                    + 0.000907 * FMath::Sin(2 * G) - 0.002697 * FMath::Cos(3 * G) + 0.00148 * FMath::Sin(3 * G);
	const double TrueSolarMin = InHour * 60.0 + EqTimeMin + 4.0 * Longitude - 60.0 * TimeZone;
	const double HourAngle = FMath::DegreesToRadians(TrueSolarMin / 4.0 - 180.0);
	const double Lat = FMath::DegreesToRadians(static_cast<double>(Latitude));

	const double SinEl = FMath::Sin(Lat) * FMath::Sin(Decl) + FMath::Cos(Lat) * FMath::Cos(Decl) * FMath::Cos(HourAngle);
	OutElevationDeg = static_cast<float>(FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(SinEl, -1.0, 1.0))));
	const double AzFromSouth = FMath::Atan2(FMath::Sin(HourAngle),
	                                        FMath::Cos(HourAngle) * FMath::Sin(Lat) - FMath::Tan(Decl) * FMath::Cos(Lat));
	OutAzimuthDeg = static_cast<float>(FMath::Fmod(FMath::RadiansToDegrees(AzFromSouth) + 540.0, 360.0));
}

void AFDTimeOfDay::ComputeSunriseSunset(float& OutSunrise, float& OutSunset) const
{
	// 5 分ごとに高度を調べ、地平線を越える前後で直線補間する
	constexpr float Horizon = -0.83f;
	constexpr float Step = 5.f / 60.f;
	float Az = 0.f;
	float PrevEl = 0.f;
	ComputeSun(0.f, Az, PrevEl);
	for (float H = Step; H <= 24.f; H += Step)
	{
		float El = 0.f;
		ComputeSun(H, Az, El);
		const float T = (Horizon - PrevEl) / (El - PrevEl);
		if (PrevEl < Horizon && El >= Horizon)
		{
			OutSunrise = H - Step + Step * T;
		}
		else if (PrevEl >= Horizon && El < Horizon)
		{
			OutSunset = H - Step + Step * T;
		}
		PrevEl = El;
	}
}

FVector AFDTimeOfDay::DirectionFromAzEl(float AzimuthDeg, float ElevationDeg) const
{
	// 升目を回していなければ UE の +X が東、-Y が北 (setup_project.py の NORTH_OFFSET と同じ向き)。
	// 回しているときは東が (cos, sin)、北が (sin, -cos) (tools/terrain/geo.py)
	const float Az = FMath::DegreesToRadians(AzimuthDeg);
	const float El = FMath::DegreesToRadians(ElevationDeg);
	const float Rot = FMath::DegreesToRadians(GridRotationDeg);
	const FVector East(FMath::Cos(Rot), FMath::Sin(Rot), 0.f);
	const FVector North(FMath::Sin(Rot), -FMath::Cos(Rot), 0.f);
	return (East * FMath::Sin(Az) + North * FMath::Cos(Az)) * FMath::Cos(El) + FVector::UpVector * FMath::Sin(El);
}

FFDLookKey AFDTimeOfDay::EvaluateLook(float Elevation) const
{
	if (Looks.Num() == 0)
	{
		return FFDLookKey();
	}
	if (Elevation <= Looks[0].SunElevationDeg)
	{
		return Looks[0];
	}
	for (int32 i = 1; i < Looks.Num(); ++i)
	{
		const FFDLookKey& A = Looks[i - 1];
		const FFDLookKey& B = Looks[i];
		if (Elevation > B.SunElevationDeg)
		{
			continue;
		}
		const float T = (Elevation - A.SunElevationDeg) / FMath::Max(B.SunElevationDeg - A.SunElevationDeg, 0.01f);
		FFDLookKey Out;
		Out.SunElevationDeg = Elevation;
		Out.ExposureEV100 = FMath::Lerp(A.ExposureEV100, B.ExposureEV100, T);
		Out.FogTint = FMath::Lerp(A.FogTint, B.FogTint, T);
		Out.SunGlow = FMath::Lerp(A.SunGlow, B.SunGlow, T);
		Out.FogForwardScatter = FMath::Lerp(A.FogForwardScatter, B.FogForwardScatter, T);
		Out.BloomIntensity = FMath::Lerp(A.BloomIntensity, B.BloomIntensity, T);
		Out.Saturation = FMath::Lerp(A.Saturation, B.Saturation, T);
		Out.ColorGain = FMath::Lerp(A.ColorGain, B.ColorGain, T);
		return Out;
	}
	return Looks.Last();
}

void AFDTimeOfDay::Apply()
{
	float SunAzimuth = 0.f;
	ComputeSun(Hour, SunAzimuth, SunElevationDeg);

	// 太陽。光は向いている方向 (前方) へ進むので、太陽へ向かう方向の逆に向ける
	if (SunLight)
	{
		SunLight->SetWorldRotation((-DirectionFromAzEl(SunAzimuth, SunElevationDeg)).Rotation());
		SunLight->SetVisibility(SunElevationDeg > SunOffBelowDeg);
		// 日没後は空と雲を照らす光を少しずつ (指数的に) 弱める。-12° で消すときに急に暗くならないように
		const float Fade = 1.f - FMath::SmoothStep(SunOffBelowDeg, SunFadeStartDeg, SunElevationDeg);
		SunLight->SetIntensity(SunLux * FMath::Pow(10.f, -SunFadeDecades * Fade));
	}

	// 月。太陽が沈むと明るくなる (-2° で点き始め、-8° で満月の明るさ)。太陽の光が弱まる間も地面が見えるように
	const float MoonAmount = 1.f - FMath::SmoothStep(-8.f, -2.f, SunElevationDeg);
	MoonLight->SetWorldRotation((-DirectionFromAzEl(MoonAzimuthDeg, MoonElevationDeg)).Rotation());
	MoonLight->SetIntensity(MoonLux * MoonAmount);
	MoonLight->SetVisibility(MoonAmount > 0.001f);

	// 太陽と月が両方見えている間は、水・霧・半透明に使う主の光を1つに決めないと警告が出る。
	// 月が半分以上の明るさになったら月を主にする (優先度の高い方が選ばれる)
	const bool bMoonMain = MoonAmount > 0.5f;
	MoonLight->SetForwardShadingPriority(bMoonMain ? 1 : 0);
	if (SunLight)
	{
		SunLight->SetForwardShadingPriority(bMoonMain ? 0 : 1);
	}

	const FFDLookKey Look = EvaluateLook(SunElevationDeg);

	if (Fog)
	{
		// 一定の色の霧は露出に関係なく同じ明るさで足されるので、露出に合わせて明るさを変える
		// (そのままだと夜は霧だけが明るく光り、画面が灰色になる)
		const float ExposureScale = FMath::Pow(2.f, Look.ExposureEV100 - FogReferenceEV);
		Fog->SetFogInscatteringColor(DefaultFogColor * Look.FogTint * ExposureScale);
		Fog->SetDirectionalInscatteringColor(Look.SunGlow);
		Fog->SetVolumetricFogScatteringDistribution(Look.FogForwardScatter);

		// 朝もや: 3-11時の、日の出の少し前から太陽が 15° に上がるまで
		const bool bMorning = Hour >= 3.f && Hour < 11.f;
		const float Mist = bMorning ? FMath::SmoothStep(-12.f, -4.f, SunElevationDeg) * (1.f - FMath::SmoothStep(2.f, 15.f, SunElevationDeg)) : 0.f;
		Fog->SetFogDensity(BaseFogDensity * FMath::Lerp(1.f, MorningMistScale, Mist));
	}

	if (PostProcess)
	{
		FPostProcessSettings& S = PostProcess->Settings;
		S.bOverride_AutoExposureMinBrightness = true;
		S.AutoExposureMinBrightness = Look.ExposureEV100 - ExposureRangeEV;
		S.bOverride_AutoExposureMaxBrightness = true;
		S.AutoExposureMaxBrightness = Look.ExposureEV100 + ExposureRangeEV;
		S.bOverride_AutoExposureSpeedUp = true;
		S.AutoExposureSpeedUp = ExposureAdaptSpeed;
		S.bOverride_AutoExposureSpeedDown = true;
		S.AutoExposureSpeedDown = ExposureAdaptSpeed;
		S.bOverride_BloomIntensity = true;
		S.BloomIntensity = Look.BloomIntensity;
		S.bOverride_ColorSaturation = true;
		S.ColorSaturation = FVector4(Look.Saturation, Look.Saturation, Look.Saturation, 1.f);
		S.bOverride_ColorGain = true;
		S.ColorGain = FVector4(Look.ColorGain.R, Look.ColorGain.G, Look.ColorGain.B, 1.f);
	}

	ApplyNight();
}

float AFDTimeOfDay::ComputeLocalSiderealAngle(float InHour) const
{
	// グリニッジ平均恒星時 (時) = 18.697374558 + 24.06570982441908 * (J2000.0 からの日数)
	const int32 M = FMath::Clamp(Month, 1, 12);
	const FDateTime Date(2026, M, FMath::Clamp(Day, 1, FDateTime::DaysInMonth(2026, M)));
	const double DaysSinceJ2000 = Date.GetJulianDay() + (InHour - TimeZone) / 24.0 - 2451545.0;
	const double Gmst = 18.697374558 + 24.06570982441908 * DaysSinceJ2000;
	const double Lst = FMath::Fmod(Gmst + Longitude / 15.0, 24.0);
	return static_cast<float>((Lst < 0.0 ? Lst + 24.0 : Lst) / 24.0 * 2.0 * PI);
}

float AFDTimeOfDay::HouseLightsShare(float InHour) const
{
	const int32 Num = HouseLightsByHour.Num();
	if (Num == 0)
	{
		return 0.f;
	}
	const float H = FMath::Fmod(FMath::Fmod(InHour, 24.f) + 24.f, 24.f) * Num / 24.f;
	const int32 I0 = FMath::FloorToInt(H) % Num;
	return FMath::Lerp(HouseLightsByHour[I0], HouseLightsByHour[(I0 + 1) % Num], H - FMath::FloorToFloat(H));
}

void AFDTimeOfDay::ApplyNight()
{
	// 防犯灯は明るさのセンサーで点くので、日の入りの少し前から点き始める
	const float LightsOn = 1.f - FMath::SmoothStep(NightLightsOnBelowDeg - NightLightsFadeDeg, NightLightsOnBelowDeg, SunElevationDeg);
	for (AFDNightLights* Lights : NightLights)
	{
		if (Lights)
		{
			Lights->SetOnAmount(LightsOn);
		}
	}

	UWorld* World = GetWorld();
	UMaterialParameterCollectionInstance* Params = (World && NightCollection) ? World->GetParameterCollectionInstance(NightCollection) : nullptr;
	if (!Params)
	{
		return;
	}
	Params->SetScalarParameterValue(TEXT("NightLights"), LightsOn);
	Params->SetScalarParameterValue(TEXT("StarRotation"), ComputeLocalSiderealAngle(Hour));
	Params->SetScalarParameterValue(TEXT("StarBrightness"), StarBrightness);
	Params->SetScalarParameterValue(TEXT("MilkyWayBrightness"), MilkyWayBrightness);
	Params->SetScalarParameterValue(TEXT("CityGlowBrightness"), CityGlowBrightness);
	const double LatRad = FMath::DegreesToRadians(static_cast<double>(Latitude));
	Params->SetScalarParameterValue(TEXT("SinLatitude"), static_cast<float>(FMath::Sin(LatRad)));
	Params->SetScalarParameterValue(TEXT("CosLatitude"), static_cast<float>(FMath::Cos(LatRad)));
	const double RotRad = FMath::DegreesToRadians(static_cast<double>(GridRotationDeg));
	Params->SetScalarParameterValue(TEXT("SinGridRotation"), static_cast<float>(FMath::Sin(RotRad)));
	Params->SetScalarParameterValue(TEXT("CosGridRotation"), static_cast<float>(FMath::Cos(RotRad)));
	// 家の窓: 暗くなるにつれて灯り、灯っている割合は時刻で変わる (建物の壁のマテリアルが窓ごとの乱数と比べる)
	const float Dark = 1.f - FMath::SmoothStep(HouseLightsOnBelowDeg - HouseLightsFadeDeg, HouseLightsOnBelowDeg, SunElevationDeg);
	Params->SetScalarParameterValue(TEXT("HouseLights"), Dark * HouseLightsShare(Hour));
}
