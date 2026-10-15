#include "FDGameMenu.h"

#include "Engine/LocalPlayer.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "FDBigMap.h"
#include "FDBikePawn.h"
#include "FDCourseInfo.h"
#include "FDFlyPawn.h"
#include "FDTimeOfDay.h"
#include "FDTravelPoint.h"
#include "FDWalkerCharacter.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
	/** 地面を探す高さ (FDBikePawn の戻り先の探し方と同じ) */
	constexpr float LandTraceTopZ = 100000.f;
	constexpr float LandTraceBottomZ = -20000.f;
	/** これより低い地面は海とみなす (cm) */
	constexpr float LandMinZ = 20.f;

	const TCHAR* OnOff(bool bOn) { return bOn ? TEXT("ON") : TEXT("OFF"); }

	FString SeasonName(int32 Month)
	{
		if (Month >= 3 && Month <= 5) return TEXT("春");
		if (Month >= 6 && Month <= 8) return TEXT("夏");
		if (Month >= 9 && Month <= 11) return TEXT("秋");
		return TEXT("冬");
	}

	FString CameraName(EFDBikeCameraMode Mode)
	{
		switch (Mode)
		{
		case EFDBikeCameraMode::ChaseNear: return TEXT("後ろ (近く)");
		case EFDBikeCameraMode::Helmet:    return TEXT("ライダーの目線");
		default:                           return TEXT("後ろ (遠く)");
		}
	}

	FString ClockText(float Hour)
	{
		const int32 Minutes = FMath::FloorToInt(FMath::Fmod(Hour + 24.f, 24.f) * 60.f);
		return FString::Printf(TEXT("%d:%02d"), Minutes / 60, Minutes % 60);
	}
}

AFDGameMenu::AFDGameMenu()
{
	PrimaryActorTick.bCanEverTick = false;
}

void AFDGameMenu::BeginPlay()
{
	Super::BeginPlay();
	CreateInput();
}

void AFDGameMenu::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Menu.Close();
	Super::EndPlay(EndPlayReason);
}

APlayerController* AFDGameMenu::GetPC() const
{
	return GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
}

AFDTimeOfDay* AFDGameMenu::FindTimeOfDay() const
{
	if (UWorld* World = GetWorld())
	{
		if (TActorIterator<AFDTimeOfDay> It(World); It)
		{
			return *It;
		}
	}
	return nullptr;
}

// ---------------------------------------------------------------- 入力

void AFDGameMenu::CreateInput()
{
	APlayerController* PC = GetPC();
	if (!PC)
	{
		return;
	}

	// 入力アセットはコードで作る (FDBikePawn と同じ)。バイクに乗っていても降りていても飛んでいても効く
	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_GameMenu"));
	MenuAction = NewObject<UInputAction>(this, TEXT("IA_GameMenu"));
	MenuAction->ValueType = EInputActionValueType::Boolean;
	MappingContext->MapKey(MenuAction, EKeys::Tab);
	MappingContext->MapKey(MenuAction, EKeys::Gamepad_Special_Right);
	MapAction = NewObject<UInputAction>(this, TEXT("IA_BigMap"));
	MapAction->ValueType = EInputActionValueType::Boolean;
	MappingContext->MapKey(MapAction, EKeys::M);

	if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
			ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
	{
		Subsystem->AddMappingContext(MappingContext, 2);
	}

	EnableInput(PC);
	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(InputComponent);
	if (!Input)
	{
		UE_LOG(LogTemp, Error, TEXT("FDGameMenu: Enhanced Input が有効になっていません"));
		return;
	}
	Input->BindActionValueLambda(MenuAction, ETriggerEvent::Started, [this](const FInputActionValue&) { ToggleMenu(); });
	Input->BindActionValueLambda(MapAction, ETriggerEvent::Started, [this](const FInputActionValue&) { ToggleMap(); });
}

// ---------------------------------------------------------------- メニュー

void AFDGameMenu::ToggleMenu()
{
	if (Menu.IsOpen())
	{
		Menu.Close();
		return;
	}
	OpenMain();
}

void AFDGameMenu::OpenMain(int32 FocusIndex)
{
	APlayerController* PC = GetPC();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	if (!Pawn)
	{
		return;
	}
	AFDBikePawn* Bike = Cast<AFDBikePawn>(Pawn);
	AFDWalkerCharacter* Walker = Cast<AFDWalkerCharacter>(Pawn);
	AFDFlyPawn* Fly = Cast<AFDFlyPawn>(Pawn);
	AFDTimeOfDay* Time = FindTimeOfDay();

	TArray<FFDMenu::FItem> Items;
	// 切り替える行は、切り替えたあと同じ行にカーソルを置いて開き直す
	auto AddToggle = [this, &Items](const FString& Label, TFunction<void()> Apply)
	{
		const int32 Index = Items.Num();
		Items.Add({Label, TOptional<FLinearColor>(), false, [this, Index, Apply = MoveTemp(Apply)]()
		{
			Apply();
			OpenMain(Index);
		}});
	};
	auto AddAction = [&Items](const FString& Label, TFunction<void()> Action)
	{
		Items.Add({Label, TOptional<FLinearColor>(), false, MoveTemp(Action)});
	};

	AddAction(TEXT("地図とファストトラベル   (M)"), [this]() { ToggleMap(); });
	AddAction(TEXT("行き先の一覧   (F)"), [this]()
	{
		TWeakObjectPtr<AFDGameMenu> Self(this);
		Menu.OpenTravel(GetPC(), [Self](const AFDTravelPoint* Point)
		{
			if (Self.IsValid() && Point)
			{
				Self->TravelTo(FVector2D(Point->GetActorLocation()), static_cast<float>(Point->GetActorRotation().Yaw));
			}
		});
	});
	if (Time)
	{
		AddAction(FString::Printf(TEXT("時刻   %s   (1-4, T/G)"), *ClockText(Time->GetHour())), [this]() { OpenTimeMenu(); });
		AddToggle(FString::Printf(TEXT("季節   %s (%d/%d)   (Y)"), *SeasonName(Time->Month), Time->Month, Time->Day), [Time]()
		{
			Time->NextSeason();
		});
	}
	if (Bike)
	{
		AddToggle(FString::Printf(TEXT("カメラ   %s   (V)"), *CameraName(Bike->CameraMode)), [Bike]() { Bike->CycleCameraMode(); });
		AddAction(TEXT("車体の色"), [Bike]() { Bike->ToggleColorMenu(); });
		AddAction(TEXT("音   (N)"), [Bike]() { Bike->ToggleSoundMenu(); });
	}
	if (Bike || Walker)
	{
		AddToggle(FString::Printf(TEXT("ミニマップ   %s"), OnOff(FFDSettings::ShowMinimap())), [Bike, Walker]()
		{
			FFDSettings::SetShowMinimap(!FFDSettings::ShowMinimap());
			if (Bike)
			{
				FFDSettings::ShowMinimap() ? Bike->ShowMinimap() : Bike->HideMinimap();
			}
			if (Walker)
			{
				FFDSettings::ShowMinimap() ? Walker->ShowMinimap() : Walker->HideMinimap();
			}
		});
	}
	AddToggle(FString::Printf(TEXT("画面の文字 (速さ・時刻・操作)   %s"), OnOff(FFDSettings::ShowHelpText())), []()
	{
		FFDSettings::SetShowHelpText(!FFDSettings::ShowHelpText());
	});
	if (Bike)
	{
		AddAction(TEXT("自由に飛ぶ   (B)"), [Bike]() { Bike->StartFlying(); });
		AddAction(TEXT("バイクを降りる   (E、止まってから)"), [Bike]() { Bike->GetOff(); });
	}
	if (Walker)
	{
		AddAction(TEXT("自由に飛ぶ   (B)"), [Walker]() { Walker->StartFlying(); });
		if (Walker->GetBike())
		{
			AddAction(TEXT("バイクのところへ戻る   (R)"), [Walker]() { Walker->ReturnToBike(); });
		}
	}
	if (Fly)
	{
		AddAction(TEXT("地上に戻る   (B)"), [Fly]() { Fly->ReturnToGround(); });
	}
	AddAction(TEXT("閉じる   (Tab)"), []() {});

	OpenKind = EOpen::Main;
	Menu.Open(PC, TEXT("メニュー"), MoveTemp(Items), TEXT("Tab キーで閉じる"), FocusIndex);
}

void AFDGameMenu::OpenTimeMenu()
{
	AFDTimeOfDay* Time = FindTimeOfDay();
	if (!Time)
	{
		return;
	}
	static const TCHAR* const Names[] = {TEXT("朝   (1)"), TEXT("昼   (2)"), TEXT("夕方   (3)"), TEXT("夜   (4)")};
	TArray<FFDMenu::FItem> Items;
	for (int32 i = 0; i < static_cast<int32>(UE_ARRAY_COUNT(Names)); ++i)
	{
		const float Hour = Time->PresetHour(i);
		Items.Add({FString::Printf(TEXT("%s   %s"), Names[i], *ClockText(Hour)), TOptional<FLinearColor>(), false, [Time, Hour]()
		{
			Time->GoToHour(Hour);
		}});
	}
	Items.Add({TEXT("もどる"), TOptional<FLinearColor>(), false, [this]() { OpenMain(); }});
	OpenKind = EOpen::Main;
	Menu.Open(GetPC(), FString::Printf(TEXT("時刻   いま %s"), *ClockText(Time->GetHour())), MoveTemp(Items),
	          TEXT("T / G を押している間は時間が進む / 戻る"));
}

// ---------------------------------------------------------------- 拡大マップ

void AFDGameMenu::ToggleMap()
{
	if (Menu.IsOpen() && OpenKind == EOpen::Map)
	{
		Menu.Close();
		return;
	}
	APlayerController* PC = GetPC();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	UWorld* World = GetWorld();
	if (!Pawn || !World)
	{
		return;
	}

	// 地図の画像と範囲はミニマップと同じ (コースの AFDCourseInfo、無ければバイクの既定値)
	AFDBikePawn* AnyBike = nullptr;
	if (TActorIterator<AFDBikePawn> It(World); It)
	{
		AnyBike = *It;
	}
	TSoftObjectPtr<UTexture2D> Texture;
	FVector2D MapMin = FVector2D::ZeroVector;
	FVector2D MapMax = FVector2D::ZeroVector;
	if (AnyBike)
	{
		Texture = AnyBike->MinimapTexture;
		MapMin = AnyBike->MinimapWorldMin;
		MapMax = AnyBike->MinimapWorldMax;
	}
	float GridRotationDeg = 0.f;
	if (const AFDCourseInfo* Course = AFDCourseInfo::Find(World))
	{
		GridRotationDeg = Course->GridRotationDeg;
		if (Course->HasMinimapBounds())
		{
			MapMin = Course->MinimapWorldMin;
			MapMax = Course->MinimapWorldMax;
		}
		if (!Course->MinimapTexture.IsNull())
		{
			Texture = Course->MinimapTexture;
		}
	}
	LoadedMapTexture = Texture.IsNull() ? nullptr : Texture.LoadSynchronous();

	TArray<SFDBigMap::FPoint> Points;
	TArray<TWeakObjectPtr<AFDTravelPoint>> PointActors;
	for (AFDTravelPoint* Point : FFDMenu::GetTravelPoints(World))
	{
		Points.Add({FVector2D(Point->GetActorLocation()), Point->DisplayName.IsEmpty() ? Point->GetName() : Point->DisplayName});
		PointActors.Add(Point);
	}

	// 歩いている / 飛んでいるときは止めてあるバイクも出す
	const AActor* Parked = nullptr;
	if (const AFDWalkerCharacter* Walker = Cast<AFDWalkerCharacter>(Pawn))
	{
		Parked = Walker->GetBike();
	}
	else if (!Pawn->IsA<AFDBikePawn>())
	{
		Parked = AnyBike;
	}

	TWeakObjectPtr<AFDGameMenu> Self(this);
	TSharedRef<SFDBigMap> Map = SNew(SFDBigMap)
		.Player(Pawn)
		.ParkedBike(Parked)
		.MapTexture(LoadedMapTexture)
		.MapMin(MapMin)
		.MapMax(MapMax)
		.Points(Points)
		.GridRotationDeg(GridRotationDeg)
		.OnPick_Lambda([Self, PointActors](const FVector2D& Clicked, int32 PointIndex) -> FString
		{
			if (!Self.IsValid())
			{
				return FString();
			}
			if (PointActors.IsValidIndex(PointIndex) && PointActors[PointIndex].IsValid())
			{
				const AFDTravelPoint* Point = PointActors[PointIndex].Get();
				return Self->TravelTo(FVector2D(Point->GetActorLocation()), static_cast<float>(Point->GetActorRotation().Yaw));
			}
			return Self->TravelTo(Clicked, TOptional<float>());
		});

	const FSlateBrush* White = FCoreStyle::Get().GetBrush(TEXT("GenericWhiteBox"));
	TSharedRef<SWidget> Content = SNew(SBorder).BorderImage(White).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.55f)).Padding(FMargin(40.f, 24.f))
	[
		SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 0.f, 0.f, 10.f)
		[
			SNew(STextBlock)
			.Text(FText::FromString(TEXT("地図   クリックした所へファストトラベル")))
			.Font(FCoreStyle::GetDefaultFontStyle("Bold", 22))
			.ColorAndOpacity(FLinearColor::White)
		]
		+ SVerticalBox::Slot().FillHeight(1.f)
		[
			Map
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 10.f, 0.f, 0.f)
		[
			SNew(STextBlock)
			.Text(FText::FromString(TEXT("◆ 行き先   ■ 止めてあるバイク   ホイールで拡大・縮小、ドラッグで移動   M か Tab キーで閉じる")))
			.Font(FCoreStyle::GetDefaultFontStyle("Regular", 13))
			.ColorAndOpacity(FLinearColor(0.85f, 0.85f, 0.85f))
		]
	];
	OpenKind = EOpen::Map;
	Menu.OpenWidget(PC, Content, Map);
}

// ---------------------------------------------------------------- ファストトラベル

bool AFDGameMenu::FindLand(const FVector2D& XY, FVector& OutPoint) const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(FDGameMenuLand), false);
	if (const APlayerController* PC = GetPC(); PC && PC->GetPawn())
	{
		Params.AddIgnoredActor(PC->GetPawn());
	}
	const FVector Start(XY.X, XY.Y, LandTraceTopZ);
	const FVector End(XY.X, XY.Y, LandTraceBottomZ);
	for (int32 Attempt = 0; Attempt < 6; ++Attempt)
	{
		FHitResult Hit;
		if (!World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
		{
			return false;
		}
		// 海面 (Water) と、始点が中に入っているもの (遠景の地形の大きな箱など) は地面ではない (FDBikePawn と同じ)
		const AActor* HitActor = Hit.GetActor();
		if (HitActor && (Hit.bStartPenetrating || HitActor->GetClass()->GetName().Contains(TEXT("Water"))))
		{
			Params.AddIgnoredActor(HitActor);
			continue;
		}
		OutPoint = Hit.ImpactPoint;
		return OutPoint.Z >= LandMinZ;
	}
	return false;
}

FString AFDGameMenu::TravelTo(const FVector2D& XY, TOptional<float> Yaw)
{
	APlayerController* PC = GetPC();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	if (!Pawn)
	{
		return TEXT("移動できません");
	}

	if (AFDFlyPawn* Fly = Cast<AFDFlyPawn>(Pawn))
	{
		// 飛んでいるときは海の上へも行ける
		Menu.Close();
		Fly->FlyTo(XY);
		return FString();
	}

	FVector Land;
	if (!FindLand(XY, Land))
	{
		return TEXT("海の上には移動できません");
	}
	const float FacingYaw = Yaw.IsSet() ? Yaw.GetValue() : static_cast<float>(Pawn->GetActorRotation().Yaw);
	const FTransform Where(FRotator(0.f, FacingYaw, 0.f), Land);
	Menu.Close();
	if (AFDBikePawn* Bike = Cast<AFDBikePawn>(Pawn))
	{
		Bike->TravelToTransform(Where);
	}
	else if (AFDWalkerCharacter* Walker = Cast<AFDWalkerCharacter>(Pawn))
	{
		Walker->TravelToTransform(Where);
	}
	return FString();
}
