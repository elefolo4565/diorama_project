#include "FDBikePawn.h"

#include "Camera/CameraComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SphereComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "FDBikeAudio.h"
#include "FDFlyPawn.h"
#include "FDCourseInfo.h"
#include "FDMinimap.h"
#include "FDTravelPoint.h"
#include "FDWalkerCharacter.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/ConfigCacheIni.h"
#include "Widgets/Layout/SBox.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	constexpr float Gravity = 9.81f;          // m/s^2
	constexpr float RideHeightCm = 35.f;      // 当たり判定の球の中心の、地面からの高さ
	constexpr float SafePointInterval = 1.f;  // 戻り先を更新する間隔 (秒)
	constexpr int32 DebugMessageKey = 7101;
	constexpr int32 HintMessageKey = 7103;
	// 戻るときに地面を探す高さの範囲 (cm)。開始地点が地面の下や空中でも地表に下ろせるように広く取る
	constexpr float ResetTraceTopZ = 100000.f;
	constexpr float ResetTraceBottomZ = -20000.f;

	// ステアリングの軸。tools/vehicle/build_crosscub.py と同じ値にする (メッシュはこの軸の上端を原点に作ってある)
	constexpr float RakeDeg = 27.f;       // キャスター角
	constexpr float TrailCm = 7.8f;
	constexpr float HeadTopZCm = 95.f;    // 軸の上端 (ハンドルの付け根) の高さ

	// ライトの位置 (車体の座標、cm)。メッシュのレンズの位置に合わせる
	const FVector HeadlightBikeLocation(38.f, 0.f, 98.5f);
	const FVector TailLightBikeLocation(-99.f, 0.f, 70.f);
	constexpr float TailLightLumens = 15.f;

	// M_FD_VehiclePaint / M_FD_VehicleLight (setup_project.py が作る) のパラメータ
	const TCHAR* const ColorParam = TEXT("Color");
	const TCHAR* const IntensityParam = TEXT("Intensity");
	const TCHAR* const RoughnessParam = TEXT("Roughness");

	// 車体色の一覧 (ECrossCubColor の順)。名前はパッケージ版でも出せるよう UENUM の表示名とは別に持つ
	struct FPaintPreset
	{
		const TCHAR* Name;
		FLinearColor Color;  // リニア
		float Roughness;     // つや消しは粗く
	};
	const FPaintPreset PaintPresets[] = {
		{TEXT("\u30a4\u30a8\u30ed\u30fc"), FLinearColor(0.80f, 0.50f, 0.02f), 0.28f},                    // イエロー
		{TEXT("\u30db\u30ef\u30a4\u30c8"), FLinearColor(0.78f, 0.78f, 0.74f), 0.30f},                    // ホワイト
		{TEXT("\u30de\u30c3\u30c8\u30b0\u30ea\u30fc\u30f3"), FLinearColor(0.10f, 0.13f, 0.06f), 0.65f},  // マットグリーン
		{TEXT("\u30de\u30c3\u30c8\u30b0\u30ec\u30fc"), FLinearColor(0.20f, 0.21f, 0.21f), 0.65f},        // マットグレー
		{TEXT("\u30ec\u30c3\u30c9"), FLinearColor(0.55f, 0.03f, 0.02f), 0.28f},                          // レッド
		{TEXT("\u30d6\u30eb\u30fc"), FLinearColor(0.03f, 0.12f, 0.40f), 0.28f},                          // ブルー
	};
	constexpr int32 NumPaintPresets = UE_ARRAY_COUNT(PaintPresets);
	constexpr float CustomPaintRoughness = 0.3f;

	// メニューで選んだ色の保存先 (Saved/Config/<Platform>/GameUserSettings.ini)
	const TCHAR* const SaveSection = TEXT("FukuokaDrive.CrossCub");
	const TCHAR* const SaveKey = TEXT("BodyColorPreset");
	const TCHAR* const CameraSaveKey = TEXT("CameraMode");
	constexpr int32 NumCameraModes = 3;
	const TCHAR* const EngineSoundKey = TEXT("EngineSound");
	// 前の版の WindSound / RoadSound とは別の音なので、別の名前で保存する
	const TCHAR* const WaveSoundKey = TEXT("WaveSound");
	const TCHAR* const WindSoundKey = TEXT("WindNoiseSound");

	// 海の近さを測る: バイクのまわりの円の上で地面を測り、海面より低い (または地形が無い) 点の割合を出す
	constexpr float SeaCheckInterval = 0.5f;          // 秒
	constexpr int32 SeaCheckDirections = 8;
	constexpr float SeaNearRadiusCm = 3000.f;         // 30m
	constexpr float SeaFarRadiusCm = 10000.f;         // 100m
	constexpr float SeaLevelZCm = 20.f;

	// 後ろのカメラの距離 (遠く / 近く)
	constexpr float ChaseArmCm = 380.f, ChaseHeightCm = 95.f, ChasePitchDeg = -8.f;
	constexpr float NearArmCm = 250.f, NearHeightCm = 70.f, NearPitchDeg = -6.f;

	// glTF の取り込み (Interchange) はメッシュを <名前>/StaticMeshes/<名前> に置く
	TSoftObjectPtr<UStaticMesh> VehicleMesh(const TCHAR* Name)
	{
		return TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(FString::Printf(TEXT("/Game/FukuokaDrive/Vehicle/%s/StaticMeshes/%s.%s"), Name, Name, Name)));
	}

	/** マテリアルのスロット名 (glTF のマテリアル名) か、今のマテリアルの名前に Key を含むか */
	bool SlotMatches(const UStaticMeshComponent* Comp, int32 Index, const TCHAR* Key)
	{
		const TArray<FName> Names = Comp->GetMaterialSlotNames();
		if (Names.IsValidIndex(Index) && Names[Index].ToString().Contains(Key))
		{
			return true;
		}
		const UMaterialInterface* Material = Comp->GetMaterial(Index);
		return Material && Material->GetName().Contains(Key);
	}

	UStaticMeshComponent* MakePart(AActor* Owner, USceneComponent* Parent, const TCHAR* Name)
	{
		UStaticMeshComponent* Part = Owner->CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Part->SetupAttachment(Parent);
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Part->SetGenerateOverlapEvents(false);
		return Part;
	}
}

AFDBikePawn::AFDBikePawn()
{
	PrimaryActorTick.bCanEverTick = true;

	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(RideHeightCm);
	Collision->SetCollisionProfileName(TEXT("Pawn"));
	SetRootComponent(Collision);

	// 傾きの軸は地面の高さ (タイヤの接地線) に置く
	LeanPivot = CreateDefaultSubobject<USceneComponent>(TEXT("LeanPivot"));
	LeanPivot->SetupAttachment(Collision);
	LeanPivot->SetRelativeLocation(FVector(0.f, 0.f, -RideHeightCm));

	// 見た目のメッシュとその位置は OnConstruction (ApplyAppearance) で決める (ホイールベースなどを変えても合うように)
	BodyMeshAsset = VehicleMesh(TEXT("SM_CC_Body"));
	SteeringMeshAsset = VehicleMesh(TEXT("SM_CC_Steering"));
	WheelMeshAsset = VehicleMesh(TEXT("SM_CC_Wheel"));
	RiderMeshAsset = VehicleMesh(TEXT("SM_CC_Rider"));
	MinimapTexture = TSoftObjectPtr<UTexture2D>(FSoftObjectPath(TEXT("/Game/FukuokaDrive/UI/T_FD_Minimap.T_FD_Minimap")));

	// メッシュがまだ取り込まれていないときの仮の形 (エンジン付属の基本形状)
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	FallbackCylinder = CylinderMesh.Object;
	FallbackCube = CubeMesh.Object;

	SteerAxis = CreateDefaultSubobject<USceneComponent>(TEXT("SteerAxis"));
	SteerAxis->SetupAttachment(LeanPivot);

	Body = MakePart(this, LeanPivot, TEXT("Body"));
	Steering = MakePart(this, SteerAxis, TEXT("Steering"));
	FrontWheel = MakePart(this, Steering, TEXT("FrontWheel"));
	RearWheel = MakePart(this, LeanPivot, TEXT("RearWheel"));
	Rider = MakePart(this, LeanPivot, TEXT("Rider"));

	// ライトは車体と一緒に傾くよう LeanPivot の下に付ける。ヘッドライトはハンドルと一緒に向きが変わる
	Headlight = CreateDefaultSubobject<USpotLightComponent>(TEXT("Headlight"));
	Headlight->SetupAttachment(Steering);
	Headlight->SetIntensityUnits(ELightUnits::Lumens);
	Headlight->SetIntensity(1500.f);
	Headlight->SetLightColor(FLinearColor(1.f, 0.97f, 0.92f));
	Headlight->SetAttenuationRadius(8000.f);
	Headlight->SetInnerConeAngle(12.f);
	Headlight->SetOuterConeAngle(28.f);

	TailLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("TailLight"));
	TailLight->SetupAttachment(LeanPivot);
	TailLight->SetIntensityUnits(ELightUnits::Lumens);
	TailLight->SetIntensity(TailLightLumens);
	TailLight->SetLightColor(FLinearColor(1.f, 0.05f, 0.02f));
	TailLight->SetAttenuationRadius(300.f);
	TailLight->SetCastShadows(false);

	SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArm"));
	SpringArm->SetupAttachment(Collision);
	SpringArm->SetRelativeRotation(FRotator(-8.f, 0.f, 0.f));
	SpringArm->TargetArmLength = 380.f;
	SpringArm->SocketOffset = FVector(0.f, 0.f, 95.f);
	SpringArm->bEnableCameraLag = true;
	SpringArm->CameraLagSpeed = 8.f;
	SpringArm->bEnableCameraRotationLag = true;
	SpringArm->CameraRotationLagSpeed = 6.f;
	SpringArm->bInheritRoll = false;
	SpringArm->bUsePawnControlRotation = false;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SpringArm, USpringArmComponent::SocketName);
	Camera->SetFieldOfView(80.f);

	// ライダーの目線: 車体と一緒に傾く LeanPivot に付ける (向きは毎フレーム UpdateCamera で決める)
	HelmetCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("HelmetCamera"));
	HelmetCamera->SetupAttachment(LeanPivot);
	HelmetCamera->SetRelativeLocation(HelmetEyeLocation);
	HelmetCamera->SetFieldOfView(80.f);
	HelmetCamera->SetAutoActivate(false);

	Sound = CreateDefaultSubobject<UFDBikeAudioComponent>(TEXT("Sound"));
	Sound->SetupAttachment(Collision);

	WalkerClass = AFDWalkerCharacter::StaticClass();
}

void AFDBikePawn::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyAppearance();
}

void AFDBikePawn::BeginPlay()
{
	Super::BeginPlay();

	// メニューで前に選んだ色があればそれを使う
	int32 SavedPreset = 0;
	if (GConfig->GetInt(SaveSection, SaveKey, SavedPreset, GGameUserSettingsIni) && SavedPreset >= 0 &&
		SavedPreset < NumPaintPresets)
	{
		SetBodyColorPreset(static_cast<ECrossCubColor>(SavedPreset));
	}
	int32 SavedCamera = 0;
	if (GConfig->GetInt(SaveSection, CameraSaveKey, SavedCamera, GGameUserSettingsIni) && SavedCamera >= 0 &&
		SavedCamera < NumCameraModes)
	{
		CameraMode = static_cast<EFDBikeCameraMode>(SavedCamera);
	}
	SetCameraMode(CameraMode);
	GConfig->GetBool(SaveSection, EngineSoundKey, Sound->bEngineSound, GGameUserSettingsIni);
	GConfig->GetBool(SaveSection, WaveSoundKey, Sound->bWaveSound, GGameUserSettingsIni);
	GConfig->GetBool(SaveSection, WindSoundKey, Sound->bWindSound, GGameUserSettingsIni);
	Sound->Start();

	YawDeg = GetActorRotation().Yaw;
	SafeTransform = FTransform(FRotator(0.f, YawDeg, 0.f), GetActorLocation());
	ResetToSafePoint();
}

// ---------------------------------------------------------------- 見た目

FVector AFDBikePawn::BikeToSteerLocal(const FVector& BikePoint) const
{
	return FRotator(RakeDeg, 0.f, 0.f).UnrotateVector(BikePoint - SteerAxis->GetRelativeLocation());
}

void AFDBikePawn::ApplyAppearance()
{
	const float HalfBase = WheelbaseCm * 0.5f;
	const float RakeRad = FMath::DegreesToRadians(RakeDeg);

	// ステアリングの軸: 地面との交点がトレールの分だけ前輪の接地点より前。上端はキャスター角だけ後ろ
	const FVector AxisUp(-FMath::Sin(RakeRad), 0.f, FMath::Cos(RakeRad));
	const FVector AxisGround(HalfBase + TrailCm, 0.f, 0.f);
	SteerAxis->SetRelativeLocationAndRotation(AxisGround + AxisUp * (HeadTopZCm / AxisUp.Z), FRotator(RakeDeg, 0.f, 0.f));

	UStaticMesh* BodyMesh = BodyMeshAsset.LoadSynchronous();
	UStaticMesh* SteeringMesh = SteeringMeshAsset.LoadSynchronous();
	UStaticMesh* WheelMesh = WheelMeshAsset.LoadSynchronous();
	UStaticMesh* RiderMesh = RiderMeshAsset.LoadSynchronous();

	Body->EmptyOverrideMaterials();
	Steering->EmptyOverrideMaterials();
	if (BodyMesh)
	{
		Body->SetStaticMesh(BodyMesh);
		Body->SetRelativeTransform(FTransform::Identity);
	}
	else
	{
		Body->SetStaticMesh(FallbackCube);
		Body->SetRelativeTransform(FTransform(FRotator::ZeroRotator, FVector(0.f, 0.f, 62.f), FVector(1.15f, 0.3f, 0.35f)));
	}
	Steering->SetStaticMesh(SteeringMesh);

	const float WheelScale = WheelRadiusCm * 2.f / 100.f;
	for (UStaticMeshComponent* Wheel : {FrontWheel.Get(), RearWheel.Get()})
	{
		Wheel->SetStaticMesh(WheelMesh ? WheelMesh : FallbackCylinder.Get());
		Wheel->SetRelativeScale3D(WheelMesh ? FVector::OneVector : FVector(WheelScale, WheelScale, 0.1f));
	}
	// 仮の円柱は軸が Z なので、横倒しにして軸を Y (車軸の向き) にする
	WheelBaseRotation = WheelMesh ? FQuat::Identity : FRotator(0.f, 0.f, 90.f).Quaternion();
	FrontWheel->SetRelativeLocationAndRotation(BikeToSteerLocal(FVector(HalfBase, 0.f, WheelRadiusCm)), WheelBaseRotation);
	RearWheel->SetRelativeLocationAndRotation(FVector(-HalfBase, 0.f, WheelRadiusCm), WheelBaseRotation);

	if (RiderMesh)
	{
		Rider->SetStaticMesh(RiderMesh);
		Rider->SetRelativeTransform(FTransform::Identity);
	}
	else
	{
		Rider->SetStaticMesh(FallbackCylinder);
		Rider->SetRelativeTransform(FTransform(FRotator(-10.f, 0.f, 0.f), FVector(-12.f, 0.f, 120.f), FVector(0.4f, 0.4f, 0.75f)));
	}
	UpdateRiderVisibility();

	Headlight->SetRelativeLocationAndRotation(BikeToSteerLocal(HeadlightBikeLocation), FRotator(-4.f - RakeDeg, 0.f, 0.f));  // ロービーム: 少し下向き
	TailLight->SetRelativeLocation(TailLightBikeLocation);

	// 車体色とテールランプのレンズ (setup_project.py が専用のマテリアルに差し替えたスロット)
	PaintMaterials.Reset();
	TailLensMaterial = nullptr;
	for (UStaticMeshComponent* Comp : {Body.Get(), Steering.Get()})
	{
		if (!Comp->GetStaticMesh())
		{
			continue;
		}
		for (int32 i = 0; i < Comp->GetNumMaterials(); ++i)
		{
			if (SlotMatches(Comp, i, TEXT("Paint")))
			{
				PaintMaterials.Add(Comp->CreateDynamicMaterialInstance(i));
			}
			else if (SlotMatches(Comp, i, TEXT("TailLens")))
			{
				TailLensMaterial = Comp->CreateDynamicMaterialInstance(i);
			}
		}
	}
	TailLensBaseIntensity = TailLensMaterial ? TailLensMaterial->K2_GetScalarParameterValue(FName(IntensityParam)) : 0.f;
	ApplyPaint();
	bBrakeLightOn = false;
}

void AFDBikePawn::SetBodyColorPreset(ECrossCubColor Preset)
{
	BodyColorPreset = Preset;
	ApplyPaint();
}

void AFDBikePawn::SetBodyColor(const FLinearColor& Color)
{
	BodyColorPreset = ECrossCubColor::Custom;
	BodyColor = Color;
	ApplyPaint();
}

void AFDBikePawn::ApplyPaint()
{
	const int32 Index = static_cast<int32>(BodyColorPreset);
	const bool bPreset = Index < NumPaintPresets;
	const FLinearColor Color = bPreset ? PaintPresets[Index].Color : BodyColor;
	const float Roughness = bPreset ? PaintPresets[Index].Roughness : CustomPaintRoughness;
	for (UMaterialInstanceDynamic* Material : PaintMaterials)
	{
		if (Material)
		{
			Material->SetVectorParameterValue(FName(ColorParam), Color);
			Material->SetScalarParameterValue(FName(RoughnessParam), Roughness);
		}
	}
}

// ---------------------------------------------------------------- メニュー (車体色・ファストトラベル)

void AFDBikePawn::ToggleColorMenu()
{
	if (IsMenuOpen(EMenu::Color))
	{
		Menu.Close();
		return;
	}
	TArray<FFDMenu::FItem> Items;
	for (int32 i = 0; i < NumPaintPresets; ++i)
	{
		const ECrossCubColor Preset = static_cast<ECrossCubColor>(i);
		Items.Add({PaintPresets[i].Name, TOptional<FLinearColor>(PaintPresets[i].Color), Preset == BodyColorPreset, [this, Preset]()
		{
			SetBodyColorPreset(Preset);
			GConfig->SetInt(SaveSection, SaveKey, static_cast<int32>(Preset), GGameUserSettingsIni);
			GConfig->Flush(false, GGameUserSettingsIni);
		}});
	}
	OpenMenuKind = EMenu::Color;
	Menu.Open(Cast<APlayerController>(GetController()), TEXT("\u8eca\u4f53\u306e\u8272"),  // 車体の色
	          MoveTemp(Items), TEXT("Tab \u30ad\u30fc\u3067\u9589\u3058\u308b"));  // Tab キーで閉じる
}

void AFDBikePawn::ToggleSoundMenu()
{
	if (IsMenuOpen(EMenu::Sound))
	{
		Menu.Close();
		return;
	}
	struct FSoundEntry
	{
		const TCHAR* Name;
		bool* Flag;
		const TCHAR* Key;
	};
	const FSoundEntry Entries[] = {
		{TEXT("\u30a8\u30f3\u30b8\u30f3\u97f3"), &Sound->bEngineSound, EngineSoundKey},  // エンジン音
		{TEXT("\u6ce2\u306e\u97f3"), &Sound->bWaveSound, WaveSoundKey},                    // 波の音
		{TEXT("\u98a8\u5207\u308a\u97f3"), &Sound->bWindSound, WindSoundKey},              // 風切り音
	};
	TArray<FFDMenu::FItem> Items;
	for (const FSoundEntry& Entry : Entries)
	{
		bool* Flag = Entry.Flag;
		const TCHAR* Key = Entry.Key;
		// 今オンの音に印が付く。選ぶとオン/オフが入れ替わり、メニューを開き直して印を更新する
		Items.Add({FString::Printf(TEXT("%s  %s"), Entry.Name, *Flag ? TEXT("ON") : TEXT("OFF")), TOptional<FLinearColor>(), *Flag,
		           [this, Flag, Key]()
		{
			*Flag = !*Flag;
			GConfig->SetBool(SaveSection, Key, *Flag, GGameUserSettingsIni);
			GConfig->Flush(false, GGameUserSettingsIni);
			Menu.Close();
			ToggleSoundMenu();
		}});
	}
	OpenMenuKind = EMenu::Sound;
	Menu.Open(Cast<APlayerController>(GetController()), TEXT("\u97f3"),  // 音
	          MoveTemp(Items), TEXT("N \u30ad\u30fc\u3067\u9589\u3058\u308b"));  // N キーで閉じる
}

void AFDBikePawn::ToggleTravelMenu()
{
	if (IsMenuOpen(EMenu::Travel))
	{
		Menu.Close();
		return;
	}
	OpenMenuKind = EMenu::Travel;
	Menu.OpenTravel(Cast<APlayerController>(GetController()), [this](const AFDTravelPoint* Point) { TravelTo(Point); });
}

TArray<AFDTravelPoint*> AFDBikePawn::GetTravelPoints() const
{
	return FFDMenu::GetTravelPoints(GetWorld());
}

void AFDBikePawn::TravelTo(const AFDTravelPoint* Point)
{
	if (!Point)
	{
		return;
	}
	TravelToTransform(FTransform(FRotator(0.f, Point->GetActorRotation().Yaw, 0.f), Point->GetActorLocation()));
}

void AFDBikePawn::TravelToTransform(const FTransform& Where)
{
	// 戻り先を行き先にして、そこへ戻す (高さは上から地面を探し直す)
	SafeTransform = FTransform(FRotator(0.f, Where.Rotator().Yaw, 0.f), Where.GetLocation());
	SafePointTimer = 0.f;
	ResetToSafePoint();
}

// ---------------------------------------------------------------- ミニマップ

void AFDBikePawn::ShowMinimap()
{
	UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (Minimap.IsValid() || !bShowMinimap || !FFDSettings::ShowMinimap() || !Viewport || !IsLocallyControlled())
	{
		return;
	}
	float GridRotationDeg = 0.f;
	if (const AFDCourseInfo* Course = AFDCourseInfo::Find(GetWorld()))
	{
		GridRotationDeg = Course->GridRotationDeg;
		if (Course->HasMinimapBounds())
		{
			MinimapWorldMin = Course->MinimapWorldMin;
			MinimapWorldMax = Course->MinimapWorldMax;
		}
		if (!Course->MinimapTexture.IsNull())
		{
			MinimapTexture = Course->MinimapTexture;
		}
	}
	LoadedMinimapTexture = MinimapTexture.LoadSynchronous();
	if (!LoadedMinimapTexture)
	{
		UE_LOG(LogTemp, Warning, TEXT("FDBikePawn: ミニマップの地図 %s がありません (build_minimap.py と setup_project.py を実行)"),
		       *MinimapTexture.ToString());
	}
	TArray<FVector2D> Markers;
	for (const AFDTravelPoint* Point : GetTravelPoints())
	{
		Markers.Add(FVector2D(Point->GetActorLocation()));
	}
	Minimap = SNew(SBox).HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(FMargin(0.f, 0.f, 32.f, 32.f))
	[
		SNew(SFDMinimap)
		.Player(this)
		.MapTexture(LoadedMinimapTexture)
		.MapMin(MinimapWorldMin)
		.MapMax(MinimapWorldMax)
		.Markers(Markers)
		.Diameter(MinimapDiameter)
		.RadiusSlowM(MinimapRadiusSlowM)
		.RadiusFastM(MinimapRadiusFastM)
		.GridRotationDeg(GridRotationDeg)
	];
	Viewport->AddViewportWidgetContent(Minimap.ToSharedRef(), 5);
}

void AFDBikePawn::HideMinimap()
{
	if (!Minimap.IsValid())
	{
		return;
	}
	if (UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
	{
		Viewport->RemoveViewportWidgetContent(Minimap.ToSharedRef());
	}
	Minimap.Reset();
}

void AFDBikePawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Menu.Close();
	HideMinimap();
	Super::EndPlay(EndPlayReason);
}

void AFDBikePawn::UpdateAppearance(float DeltaSeconds)
{
	Steering->SetRelativeRotation(FRotator(0.f, SteerDeg, 0.f));

	// 車輪は走った距離だけ回す (上側が前へ進む向き)
	WheelSpinRad = FMath::Fmod(WheelSpinRad + SpeedMs * 100.f * DeltaSeconds / FMath::Max(WheelRadiusCm, 1.f), UE_TWO_PI);
	const FQuat Spin(FVector::YAxisVector, WheelSpinRad);
	FrontWheel->SetRelativeRotation(Spin * WheelBaseRotation);
	RearWheel->SetRelativeRotation(Spin * WheelBaseRotation);

	// ブレーキランプ
	const bool bBrake = BrakeInput > 0.05f;
	if (bBrake != bBrakeLightOn)
	{
		bBrakeLightOn = bBrake;
		const float Boost = bBrake ? BrakeLightBoost : 1.f;
		TailLight->SetIntensity(TailLightLumens * Boost);
		if (TailLensMaterial)
		{
			TailLensMaterial->SetScalarParameterValue(FName(IntensityParam), TailLensBaseIntensity * Boost);
		}
	}
}

// ---------------------------------------------------------------- 入力

void AFDBikePawn::CreateInputAssets()
{
	if (MappingContext)
	{
		return;
	}

	// 入力アセットはコードで作る (エディタでのアセット作成を不要にするため)
	ThrottleAction = NewObject<UInputAction>(this, TEXT("IA_Throttle"));
	ThrottleAction->ValueType = EInputActionValueType::Axis1D;
	BrakeAction = NewObject<UInputAction>(this, TEXT("IA_Brake"));
	BrakeAction->ValueType = EInputActionValueType::Axis1D;
	SteerAction = NewObject<UInputAction>(this, TEXT("IA_Steer"));
	SteerAction->ValueType = EInputActionValueType::Axis1D;
	ResetAction = NewObject<UInputAction>(this, TEXT("IA_Reset"));
	ResetAction->ValueType = EInputActionValueType::Boolean;
	TravelMenuAction = NewObject<UInputAction>(this, TEXT("IA_TravelMenu"));
	TravelMenuAction->ValueType = EInputActionValueType::Boolean;
	GetOffAction = NewObject<UInputAction>(this, TEXT("IA_GetOff"));
	GetOffAction->ValueType = EInputActionValueType::Boolean;
	CameraAction = NewObject<UInputAction>(this, TEXT("IA_Camera"));
	CameraAction->ValueType = EInputActionValueType::Boolean;
	SoundMenuAction = NewObject<UInputAction>(this, TEXT("IA_SoundMenu"));
	SoundMenuAction->ValueType = EInputActionValueType::Boolean;
	FlyAction = NewObject<UInputAction>(this, TEXT("IA_Fly"));
	FlyAction->ValueType = EInputActionValueType::Boolean;
	LookAction = NewObject<UInputAction>(this, TEXT("IA_BikeLook"));
	LookAction->ValueType = EInputActionValueType::Axis2D;
	LookStickAction = NewObject<UInputAction>(this, TEXT("IA_BikeLookStick"));
	LookStickAction->ValueType = EInputActionValueType::Axis2D;
	LookResetAction = NewObject<UInputAction>(this, TEXT("IA_BikeLookReset"));
	LookResetAction->ValueType = EInputActionValueType::Boolean;

	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_CrossCub"));

	auto MapNegated = [this](UInputAction* Action, const FKey& Key)
	{
		FEnhancedActionKeyMapping& Mapping = MappingContext->MapKey(Action, Key);
		Mapping.Modifiers.Add(NewObject<UInputModifierNegate>(MappingContext));
	};

	MappingContext->MapKey(ThrottleAction, EKeys::W);
	MappingContext->MapKey(ThrottleAction, EKeys::Up);
	MappingContext->MapKey(ThrottleAction, EKeys::Gamepad_RightTriggerAxis);

	MappingContext->MapKey(BrakeAction, EKeys::S);
	MappingContext->MapKey(BrakeAction, EKeys::Down);
	MappingContext->MapKey(BrakeAction, EKeys::SpaceBar);
	MappingContext->MapKey(BrakeAction, EKeys::Gamepad_LeftTriggerAxis);

	MappingContext->MapKey(SteerAction, EKeys::D);
	MappingContext->MapKey(SteerAction, EKeys::Right);
	MapNegated(SteerAction, EKeys::A);
	MapNegated(SteerAction, EKeys::Left);
	MappingContext->MapKey(SteerAction, EKeys::Gamepad_LeftX);

	MappingContext->MapKey(ResetAction, EKeys::R);
	MappingContext->MapKey(ResetAction, EKeys::Gamepad_FaceButton_Top);

	// 車体の色は Tab のメニューから (M は拡大マップ、ゲームパッドのメニューボタンは Tab のメニュー。AFDGameMenu)

	MappingContext->MapKey(TravelMenuAction, EKeys::F);
	MappingContext->MapKey(TravelMenuAction, EKeys::Gamepad_Special_Left);

	MappingContext->MapKey(GetOffAction, EKeys::E);
	MappingContext->MapKey(GetOffAction, EKeys::Gamepad_FaceButton_Left);

	MappingContext->MapKey(CameraAction, EKeys::V);
	MappingContext->MapKey(CameraAction, EKeys::Gamepad_RightShoulder);

	MappingContext->MapKey(SoundMenuAction, EKeys::N);
	MappingContext->MapKey(SoundMenuAction, EKeys::Gamepad_DPad_Down);

	MappingContext->MapKey(FlyAction, EKeys::B);
	MappingContext->MapKey(FlyAction, EKeys::Gamepad_DPad_Up);

	MappingContext->MapKey(LookAction, EKeys::Mouse2D);
	MappingContext->MapKey(LookStickAction, EKeys::Gamepad_Right2D).Modifiers.Add(NewObject<UInputModifierDeadZone>(MappingContext));
	MappingContext->MapKey(LookResetAction, EKeys::MiddleMouseButton);
	MappingContext->MapKey(LookResetAction, EKeys::Gamepad_RightThumbstick);
}

void AFDBikePawn::PawnClientRestart()
{
	Super::PawnClientRestart();

	CreateInputAssets();
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
				ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			Subsystem->AddMappingContext(MappingContext, 0);
		}
	}
	ShowMinimap();
}

void AFDBikePawn::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	bRidden = true;
	UpdateRiderVisibility();
}

void AFDBikePawn::UnPossessed()
{
	// 降りたあとも W などがこのバイクの操作に取られないよう、キーの割り当てを外す (Super の後は Controller が無い)
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
				ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			Subsystem->RemoveMappingContext(MappingContext);
		}
	}
	Menu.Close();
	HideMinimap();
	Super::UnPossessed();

	bRidden = false;
	ThrottleInput = 0.f;
	BrakeInput = 0.f;
	SteerInput = 0.f;
	UpdateRiderVisibility();
	if (GEngine)
	{
		GEngine->RemoveOnScreenDebugMessage(DebugMessageKey);
	}
}

// ---------------------------------------------------------------- 乗り降り

FTransform AFDBikePawn::GetDismountTransform() const
{
	const FRotator Facing(0.f, YawDeg, 0.f);
	const FVector Left = -FRotationMatrix(Facing).GetUnitAxis(EAxis::Y);
	const FVector Spot = GetActorLocation() + Left * GetOffSideCm;
	FVector Point, Normal;
	const float GroundZ = GetActorLocation().Z - RideHeightCm;
	if (TraceGroundBetween(Spot, GroundZ + 300.f, GroundZ - 600.f, Point, Normal))
	{
		return FTransform(Facing, Point);
	}
	return FTransform(Facing, FVector(Spot.X, Spot.Y, GroundZ));
}

void AFDBikePawn::GetOff()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	UWorld* World = GetWorld();
	if (!PC || !World || !WalkerClass)
	{
		return;
	}
	if (GetSpeedKmh() > MaxGetOffSpeedKmh)
	{
		if (GEngine)
		{
			// デバッグ表示のフォントは日本語を出せない
			GEngine->AddOnScreenDebugMessage(HintMessageKey, 2.f, FColor::Yellow, TEXT("Stop the bike to get off (S = brake)"));
		}
		return;
	}

	const FTransform Stand = GetDismountTransform();
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	AFDWalkerCharacter* Walker = World->SpawnActor<AFDWalkerCharacter>(
		WalkerClass, Stand.GetLocation() + FVector(0.f, 0.f, AFDWalkerCharacter::StandHeightCm), Stand.Rotator(), Params);
	if (!Walker)
	{
		return;
	}
	Walker->SetBike(this);
	SpeedMs = 0.f;
	PC->Possess(Walker);
	// カメラはバイクを後ろから見ていた向きのまま
	PC->SetControlRotation(FRotator(-12.f, YawDeg, 0.f));
}

void AFDBikePawn::StartFlying()
{
	Menu.Close();
	// 乗り手がいなくなるので、その場で止めておく
	SpeedMs = 0.f;
	AFDFlyPawn::StartFrom(this);
}

void AFDBikePawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	CreateInputAssets();
	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!Input)
	{
		UE_LOG(LogTemp, Error, TEXT("FDBikePawn: Enhanced Input が有効になっていません"));
		return;
	}

	Input->BindAction(ThrottleAction, ETriggerEvent::Triggered, this, &AFDBikePawn::OnThrottle);
	Input->BindActionValueLambda(ThrottleAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { ThrottleInput = 0.f; });
	Input->BindAction(BrakeAction, ETriggerEvent::Triggered, this, &AFDBikePawn::OnBrake);
	Input->BindActionValueLambda(BrakeAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { BrakeInput = 0.f; });
	Input->BindAction(SteerAction, ETriggerEvent::Triggered, this, &AFDBikePawn::OnSteer);
	Input->BindActionValueLambda(SteerAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { SteerInput = 0.f; });
	Input->BindAction(ResetAction, ETriggerEvent::Started, this, &AFDBikePawn::OnReset);
	Input->BindActionValueLambda(TravelMenuAction, ETriggerEvent::Started, [this](const FInputActionValue&) { ToggleTravelMenu(); });
	Input->BindActionValueLambda(GetOffAction, ETriggerEvent::Started, [this](const FInputActionValue&) { GetOff(); });
	Input->BindActionValueLambda(CameraAction, ETriggerEvent::Started, [this](const FInputActionValue&) { CycleCameraMode(); });
	Input->BindActionValueLambda(SoundMenuAction, ETriggerEvent::Started, [this](const FInputActionValue&) { ToggleSoundMenu(); });
	Input->BindActionValueLambda(FlyAction, ETriggerEvent::Started, [this](const FInputActionValue&) { StartFlying(); });
	Input->BindActionValueLambda(LookAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V)
	{
		Look(V.Get<FVector2D>() * MouseLookScale);
	});
	Input->BindActionValueLambda(LookStickAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V)
	{
		Look(V.Get<FVector2D>() * StickLookRateDeg * GetWorld()->GetDeltaSeconds());
	});
	Input->BindActionValueLambda(LookResetAction, ETriggerEvent::Started, [this](const FInputActionValue&)
	{
		FreeLookYawDeg = 0.f;
		FreeLookPitchDeg = 0.f;
	});
}

void AFDBikePawn::OnThrottle(const FInputActionValue& Value)
{
	ThrottleInput = FMath::Clamp(Value.Get<float>(), 0.f, 1.f);
}

void AFDBikePawn::OnBrake(const FInputActionValue& Value)
{
	BrakeInput = FMath::Clamp(Value.Get<float>(), 0.f, 1.f);
}

void AFDBikePawn::OnSteer(const FInputActionValue& Value)
{
	SteerInput = FMath::Clamp(Value.Get<float>(), -1.f, 1.f);
}

void AFDBikePawn::OnReset(const FInputActionValue& Value)
{
	ResetToSafePoint();
}

// ---------------------------------------------------------------- 走行

void AFDBikePawn::ResetToSafePoint()
{
	SpeedMs = 0.f;
	SteerDeg = 0.f;
	LeanDeg = 0.f;
	VerticalSpeedCms = 0.f;
	ForwardAccel = 0.f;
	LookYawDeg = 0.f;
	FreeLookYawDeg = 0.f;
	FreeLookPitchDeg = 0.f;
	Gear = 0;
	ShiftTimer = 0.f;
	YawDeg = SafeTransform.Rotator().Yaw;
	SetActorLocationAndRotation(SafeTransform.GetLocation(), FRotator(0.f, YawDeg, 0.f));

	// 地面に下ろす (開始地点が地面の下にあっても上から探して地表に出す)
	FVector Point, Normal;
	if (TraceGroundBetween(GetActorLocation(), ResetTraceTopZ, ResetTraceBottomZ, Point, Normal))
	{
		SetActorLocation(FVector(Point.X, Point.Y, Point.Z + RideHeightCm));
		bOnGround = true;
	}

	// カメラが前の場所から追いかけてこないよう、少しのあいだ遅れを切る (遅れを切ったフレームでカメラが新しい場所に移る)
	SpringArm->bEnableCameraLag = false;
	SpringArm->bEnableCameraRotationLag = false;
	CameraLagSnapFrames = 2;
}

bool AFDBikePawn::TraceGround(const FVector& At, FVector& OutPoint, FVector& OutNormal) const
{
	const float GroundZ = GetActorLocation().Z - RideHeightCm;
	return TraceGroundBetween(At, GroundZ + GroundTraceUpCm, GroundZ - GroundTraceDownCm, OutPoint, OutNormal);
}

bool AFDBikePawn::TraceGroundBetween(const FVector& At, float TopZ, float BottomZ, FVector& OutPoint, FVector& OutNormal) const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}

	const FVector Start(At.X, At.Y, TopZ);
	const FVector End(At.X, At.Y, BottomZ);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(FDBikeGround), false, this);
	// 海面 (Water プラグイン) には乗らない。当たったら除外して引き直す
	for (int32 Attempt = 0; Attempt < 4; ++Attempt)
	{
		FHitResult Hit;
		if (!World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
		{
			return false;
		}
		const AActor* HitActor = Hit.GetActor();
		// 始点がすでに中に入っているもの (遠景の地形の大きな箱など) も地面ではない
		if (HitActor && (Hit.bStartPenetrating || HitActor->GetClass()->GetName().Contains(TEXT("Water"))))
		{
			Params.AddIgnoredActor(HitActor);
			continue;
		}
		OutPoint = Hit.ImpactPoint;
		OutNormal = Hit.ImpactNormal;
		return true;
	}
	return false;
}

bool AFDBikePawn::FitGroundLine(const FVector& Location, const FVector& Forward, float& OutCenterZ, float& OutSlope) const
{
	if (GroundSmoothHalfLengthCm <= 0.f)
	{
		return false;
	}
	const int32 N = FMath::Clamp(GroundSmoothSamples, 2, 15);
	// 最小二乗で Z = a + b * x (x は前後の距離) を当てはめる
	float SumX = 0.f, SumZ = 0.f, SumXX = 0.f, SumXZ = 0.f;
	int32 Count = 0;
	FVector Point, Normal;
	for (int32 i = 0; i < N; ++i)
	{
		const float X = FMath::Lerp(-GroundSmoothHalfLengthCm, GroundSmoothHalfLengthCm, i / float(N - 1));
		if (TraceGround(Location + Forward * X, Point, Normal))
		{
			SumX += X;
			SumZ += Point.Z;
			SumXX += X * X;
			SumXZ += X * Point.Z;
			++Count;
		}
	}
	if (Count < 2)
	{
		return false;
	}
	const float Denom = Count * SumXX - SumX * SumX;
	if (FMath::Abs(Denom) < KINDA_SMALL_NUMBER)
	{
		return false;
	}
	OutSlope = (Count * SumXZ - SumX * SumZ) / Denom;
	OutCenterZ = (SumZ - OutSlope * SumX) / Count;
	return true;
}

void AFDBikePawn::UpdateGroundAndPitch(float DeltaSeconds)
{
	const FVector Forward = FRotator(0.f, YawDeg, 0.f).Vector();
	const FVector Location = GetActorLocation();
	const float HalfBase = WheelbaseCm * 0.5f;

	FVector FrontPoint, RearPoint, Normal;
	const bool bFront = TraceGround(Location + Forward * HalfBase, FrontPoint, Normal);
	const bool bRear = TraceGround(Location - Forward * HalfBase, RearPoint, Normal);

	// 坂の角度は前後に長めに測る (前輪と後輪の間だけだと、地形の小さな段差で急な坂になり、止まった所から発進できない)
	FVector AheadPoint, BehindPoint;
	if (TraceGround(Location + Forward * GradeSampleCm, AheadPoint, Normal) &&
	    TraceGround(Location - Forward * GradeSampleCm, BehindPoint, Normal))
	{
		GradeDeg = FMath::RadiansToDegrees(FMath::Atan2(AheadPoint.Z - BehindPoint.Z, GradeSampleCm * 2.f));
	}
	else if (bFront && bRear)
	{
		GradeDeg = FMath::RadiansToDegrees(FMath::Atan2(FrontPoint.Z - RearPoint.Z, WheelbaseCm));
	}

	float TargetZ = Location.Z;
	float FitZ = 0.f, FitSlope = 0.f;
	if (bFront && bRear && FitGroundLine(Location, Forward, FitZ, FitSlope))
	{
		// 舗装路の上で上下に揺れないよう、前後の地面にならした直線の上に乗る
		TargetZ = FitZ + RideHeightCm;
		PitchDeg = FMath::RadiansToDegrees(FMath::Atan(FitSlope));
	}
	else if (bFront && bRear)
	{
		TargetZ = (FrontPoint.Z + RearPoint.Z) * 0.5f + RideHeightCm;
		PitchDeg = FMath::RadiansToDegrees(FMath::Atan2(FrontPoint.Z - RearPoint.Z, WheelbaseCm));
	}
	else if (bFront || bRear)
	{
		TargetZ = (bFront ? FrontPoint.Z : RearPoint.Z) + RideHeightCm;
	}
	else
	{
		TargetZ = -BIG_NUMBER;
	}

	FVector NewLocation = Location;
	if (Location.Z > TargetZ + 5.f)
	{
		// 空中: 重力で落ちる (段差やジャンプ)
		VerticalSpeedCms -= Gravity * 100.f * DeltaSeconds;
		NewLocation.Z = FMath::Max(TargetZ, Location.Z + VerticalSpeedCms * DeltaSeconds);
		bOnGround = NewLocation.Z <= TargetZ + 1.f;
	}
	else
	{
		NewLocation.Z = TargetZ;
		VerticalSpeedCms = 0.f;
		bOnGround = true;
	}
	SetActorLocation(NewLocation);

	// 海に入った、または地面がない所に落ちたら戻す
	const float ContactZ = NewLocation.Z - RideHeightCm;
	if ((bOnGround && ContactZ < ResetBelowZCm) || NewLocation.Z < -10000.f)
	{
		ResetToSafePoint();
	}
}

void AFDBikePawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	const float Dt = FMath::Min(DeltaSeconds, 0.05f);

	if (CameraLagSnapFrames > 0 && --CameraLagSnapFrames == 0)
	{
		SpringArm->bEnableCameraLag = true;
		SpringArm->bEnableCameraRotationLag = true;
	}

	// ハンドル: 速度が上がるほど切れ角を絞る
	const float SpeedT = FMath::Clamp(SpeedMs * 3.6f / FMath::Max(SteerFadeSpeedKmh, 1.f), 0.f, 1.f);
	const float MaxSteer = FMath::Lerp(MaxSteerLowSpeedDeg, MaxSteerHighSpeedDeg, SpeedT);
	SteerDeg = FMath::FInterpTo(SteerDeg, SteerInput * MaxSteer, Dt, SteerResponse);

	// 回転数とギア (変速のあいだは駆動力が抜ける)。波の音のために海の近さも測る
	UpdateSeaAmount(Dt);
	const float DriveScale = UpdateEngine(Dt);

	// 前後方向の力
	const float PrevSpeedMs = SpeedMs;
	if (bOnGround)
	{
		const float V = SpeedMs;
		const float Drive = DriveScale * ThrottleInput * FMath::Min(MaxDriveForceN, MaxPowerW / FMath::Max(V, 0.5f));
		const float Resist = (V > 0.01f) ? DragCoefficient * V * V + RollingResistance * MassKg * Gravity : 0.f;
		float Accel = (Drive - Resist) / MassKg;
		Accel -= Gravity * FMath::Sin(FMath::DegreesToRadians(GradeDeg));
		Accel -= BrakeInput * MaxBrakeDecel;
		if (ThrottleInput < 0.05f && V > 0.01f)
		{
			Accel -= EngineBrakeDecel;
		}
		// 後退はしない (クロスカブにバックギアはない)
		SpeedMs = FMath::Max(0.f, V + Accel * Dt);
	}
	// 前後の加速度 (ブレーキで前が沈み、加速で後ろが沈む見た目に使う)
	ForwardAccel = FMath::FInterpTo(ForwardAccel, (SpeedMs - PrevSpeedMs) / FMath::Max(Dt, 1e-4f), Dt, 5.f);

	// 旋回と傾き
	const float YawRate = SpeedMs * FMath::Tan(FMath::DegreesToRadians(SteerDeg)) / (WheelbaseCm / 100.f);  // rad/s
	YawDeg = FRotator::NormalizeAxis(YawDeg + FMath::RadiansToDegrees(YawRate) * Dt);
	// ほぼ止まっているときは足で向きを変えられる (急な坂で登れなくなっても、向きを変えて下れるように)
	if (bRidden && SpeedMs < 1.f)
	{
		YawDeg = FRotator::NormalizeAxis(YawDeg + SteerInput * StandstillTurnDegPerSec * (1.f - SpeedMs) * Dt);
	}
	const float TargetLean = bRidden ? FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan(SpeedMs * YawRate / Gravity)), -MaxLeanDeg, MaxLeanDeg)
	                                 : ParkedLeanDeg;
	LeanDeg = FMath::FInterpTo(LeanDeg, TargetLean, Dt, LeanResponse);

	// 水平移動 → 地面に合わせる
	const FVector Forward = FRotator(0.f, YawDeg, 0.f).Vector();
	SetActorLocation(GetActorLocation() + Forward * SpeedMs * 100.f * Dt);
	UpdateGroundAndPitch(Dt);

	SetActorRotation(FRotator(PitchDeg, YawDeg, 0.f));
	const float DivePitch = FMath::Clamp(ForwardAccel / Gravity * PitchPerG, -4.f, 4.f);
	LeanPivot->SetRelativeRotation(FRotator(DivePitch, 0.f, LeanDeg));
	UpdateAppearance(Dt);
	UpdateCamera(Dt, FMath::RadiansToDegrees(YawRate));

	// 道路の上を走れている地点を戻り先として覚えておく
	SafePointTimer += Dt;
	if (SafePointTimer >= SafePointInterval && bOnGround && SpeedMs > 1.f && GetActorLocation().Z - RideHeightCm > 50.f)
	{
		SafePointTimer = 0.f;
		SafeTransform = FTransform(FRotator(0.f, YawDeg, 0.f), GetActorLocation());
	}

	if (bShowDebugText && FFDSettings::ShowHelpText() && bRidden && IsLocallyControlled() && GEngine)
	{
		GEngine->AddOnScreenDebugMessage(
			DebugMessageKey, 0.f, FColor::White,
			// デバッグ表示のフォントは日本語を表示できないので英数字だけにする
			FString::Printf(TEXT("%3.0f km/h   gear %d  %4.0f rpm   lean %+3.0f deg   grade %+4.1f%%   [W/S/A/D, R = reset, E = get off, V = camera, N = sound, F = travel, B = fly, M = map, Tab = menu]"),
			                GetSpeedKmh(), GetGear(), EngineRpm, LeanDeg, FMath::Tan(FMath::DegreesToRadians(GradeDeg)) * 100.f));
	}
}

// ---------------------------------------------------------------- エンジン

float AFDBikePawn::UpdateEngine(float DeltaSeconds)
{
	const int32 NumGears = GearRatios.Num();
	if (NumGears == 0 || !bRidden)
	{
		// 降りているときはエンジンを止める
		Gear = 0;
		ShiftTimer = 0.f;
		EngineLoad = 0.f;
		EngineRpm = FMath::FInterpTo(EngineRpm, 0.f, DeltaSeconds, 3.f);
		Sound->SetState(FMath::Max(EngineRpm, IdleRpm * 0.5f), 0.f, SpeedMs, false, 1.f, SeaAmount);
		return 1.f;
	}

	Gear = FMath::Clamp(Gear, 0, NumGears - 1);
	const float WheelRpm = SpeedMs / (UE_TWO_PI * WheelRadiusCm / 100.f) * 60.f;
	auto CoupledRpm = [&](int32 G) { return WheelRpm * GearRatios[G] * FinalDriveRatio; };

	// 自動で変速する (アクセルを大きく開けているほど高い回転まで引っぱる)
	if (ShiftTimer > 0.f)
	{
		ShiftTimer = FMath::Max(0.f, ShiftTimer - DeltaSeconds);
	}
	else
	{
		const float UpshiftRpm = FMath::Lerp(UpshiftRpmLight, UpshiftRpmFull, ThrottleInput);
		if (Gear < NumGears - 1 && ThrottleInput > 0.05f && CoupledRpm(Gear) > UpshiftRpm)
		{
			++Gear;
			ShiftTimer = ShiftSeconds;
		}
		else if (Gear > 0 && CoupledRpm(Gear) < DownshiftRpm)
		{
			--Gear;
			ShiftTimer = ShiftSeconds * 0.6f;
		}
	}
	const bool bShifting = ShiftTimer > 0.f;

	// 遠心クラッチ: 遅いうちは滑っていて、エンジンはアクセルに応じて回る。速くなると車輪の回転とつながる
	const float SlipRpm = IdleRpm + ThrottleInput * (ClutchRpm + 500.f - IdleRpm);
	const float TargetRpm = FMath::Min(FMath::Max(CoupledRpm(Gear), SlipRpm), MaxRpm);
	EngineRpm = FMath::FInterpTo(FMath::Max(EngineRpm, IdleRpm * 0.5f), TargetRpm, DeltaSeconds, bShifting ? 9.f : 6.f);

	// 変速中とレブリミットではアクセルが抜けた音にする
	const bool bLimiter = EngineRpm > MaxRpm - 150.f;
	const float TargetLoad = (bShifting || bLimiter) ? ThrottleInput * 0.15f : ThrottleInput;
	EngineLoad = FMath::FInterpTo(EngineLoad, TargetLoad, DeltaSeconds, 12.f);

	Sound->SetState(EngineRpm, EngineLoad, SpeedMs, true, CameraMode == EFDBikeCameraMode::Helmet ? HelmetWindScale : 1.f, SeaAmount);
	return bShifting ? 0.35f : 1.f;
}

// ---------------------------------------------------------------- カメラ

void AFDBikePawn::SetCameraMode(EFDBikeCameraMode Mode)
{
	CameraMode = Mode;
	const bool bHelmet = Mode == EFDBikeCameraMode::Helmet;
	Camera->SetActive(!bHelmet);
	HelmetCamera->SetActive(bHelmet);
	const bool bNear = Mode == EFDBikeCameraMode::ChaseNear;
	SpringArm->TargetArmLength = bNear ? NearArmCm : ChaseArmCm;
	SpringArm->SocketOffset = FVector(0.f, 0.f, bNear ? NearHeightCm : ChaseHeightCm);
	SpringArm->SetRelativeRotation(FRotator(bNear ? NearPitchDeg : ChasePitchDeg, 0.f, 0.f));
	UpdateRiderVisibility();
}

void AFDBikePawn::CycleCameraMode()
{
	const int32 Next = (static_cast<int32>(CameraMode) + 1) % NumCameraModes;
	SetCameraMode(static_cast<EFDBikeCameraMode>(Next));
	GConfig->SetInt(SaveSection, CameraSaveKey, Next, GGameUserSettingsIni);
	GConfig->Flush(false, GGameUserSettingsIni);
}

void AFDBikePawn::Look(const FVector2D& DeltaDeg)
{
	// メニューや地図を開いている間はマウスをメニューに使う
	if (FFDMenu::IsAnyOpen())
	{
		return;
	}
	FreeLookYawDeg = FRotator::NormalizeAxis(FreeLookYawDeg + DeltaDeg.X);
	FreeLookPitchDeg = FMath::Clamp(FreeLookPitchDeg + DeltaDeg.Y, -MaxLookDownDeg, MaxLookUpDeg);
	LookIdleSeconds = 0.f;
}

void AFDBikePawn::UpdateRiderVisibility()
{
	// ライダーの目線のときは自分の頭や腕が視界をふさがないよう隠す
	Rider->SetVisibility(bShowRider && bRidden && CameraMode != EFDBikeCameraMode::Helmet);
}

void AFDBikePawn::UpdateCamera(float DeltaSeconds, float YawRateDeg)
{
	// 速いほど視野を広げ、細かく揺らす
	const float SpeedT = FMath::Clamp(GetSpeedKmh() / FMath::Max(FovFullSpeedKmh, 1.f), 0.f, 1.f);
	const float Fov = BaseFov + SpeedFovAdd * SpeedT;
	ShakeTime = FMath::Fmod(ShakeTime + DeltaSeconds, 1000.f);
	auto ShakeOffset = [this](float Amp, float Freq)
	{
		return FVector(0.f, FMath::PerlinNoise1D(ShakeTime * Freq) * Amp, FMath::PerlinNoise1D(ShakeTime * Freq + 37.1f) * Amp);
	};
	const FVector SpeedShake = ShakeOffset(SpeedShakeCm * SpeedT * SpeedT, 7.f);

	// 曲がる方の先を見る
	const float LookTarget = FMath::Clamp(YawRateDeg * LookIntoTurnSeconds, -MaxLookIntoTurnDeg, MaxLookIntoTurnDeg);
	LookYawDeg = FMath::FInterpTo(LookYawDeg, LookTarget, DeltaSeconds, 3.f);

	// マウスで見回した向き。しばらく動かさずに走っていると、ゆっくり前に戻る
	LookIdleSeconds += DeltaSeconds;
	if (LookIdleSeconds > LookReturnDelaySeconds && GetSpeedKmh() > LookReturnMinKmh)
	{
		FreeLookYawDeg = FMath::FInterpTo(FreeLookYawDeg, 0.f, DeltaSeconds, 1.5f);
		FreeLookPitchDeg = FMath::FInterpTo(FreeLookPitchDeg, 0.f, DeltaSeconds, 1.5f);
	}

	if (CameraMode == EFDBikeCameraMode::Helmet)
	{
		const float EngineAmp = bRidden ? EngineShakeCm * (0.5f + 0.5f * EngineLoad) : 0.f;
		HelmetCamera->SetFieldOfView(Fov);
		HelmetCamera->SetRelativeLocation(HelmetEyeLocation + SpeedShake + ShakeOffset(EngineAmp, 23.f));
		// 頭は車体ほど傾けない (首で起こす)
		const float Pitch = FMath::Clamp(PitchDeg + HelmetPitchDeg + FreeLookPitchDeg, -89.f, 89.f);
		HelmetCamera->SetWorldRotation(FRotator(Pitch, YawDeg + LookYawDeg + FreeLookYawDeg, LeanDeg * HelmetLeanFollow));
	}
	else
	{
		// 横と下はアームごと回り込み、上を見るときはアームを地面に潜らせずカメラだけ上を向ける
		const bool bNear = CameraMode == EFDBikeCameraMode::ChaseNear;
		const float WantPitch = (bNear ? NearPitchDeg : ChasePitchDeg) + FreeLookPitchDeg;
		const float ArmPitch = FMath::Clamp(WantPitch, -75.f, 0.f);
		SpringArm->SetRelativeRotation(FRotator(ArmPitch, FreeLookYawDeg, 0.f));
		Camera->SetFieldOfView(Fov);
		Camera->SetRelativeLocationAndRotation(SpeedShake, FRotator(WantPitch - ArmPitch, 0.f, LeanDeg * ChaseLeanFollow));
	}
}

void AFDBikePawn::UpdateSeaAmount(float DeltaSeconds)
{
	SeaCheckTimer -= DeltaSeconds;
	if (SeaCheckTimer > 0.f)
	{
		return;
	}
	SeaCheckTimer = SeaCheckInterval;

	const FVector Center = GetActorLocation();
	auto SeaFraction = [&](float Radius)
	{
		int32 SeaPoints = 0;
		for (int32 i = 0; i < SeaCheckDirections; ++i)
		{
			const float Angle = UE_TWO_PI * i / SeaCheckDirections;
			const FVector At = Center + FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.f) * Radius;
			FVector Point, Normal;
			if (!TraceGroundBetween(At, ResetTraceTopZ, ResetTraceBottomZ, Point, Normal) || Point.Z < SeaLevelZCm)
			{
				++SeaPoints;
			}
		}
		return static_cast<float>(SeaPoints) / SeaCheckDirections;
	};
	// 波打ち際 (30m 以内に海) で大きく、100m 先に海が見える程度なら小さく
	SeaAmount = FMath::Clamp(1.4f * SeaFraction(SeaNearRadiusCm) + 0.6f * SeaFraction(SeaFarRadiusCm), 0.f, 1.f);
}
