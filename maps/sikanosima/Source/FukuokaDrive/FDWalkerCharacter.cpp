#include "FDWalkerCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "FDBikePawn.h"
#include "FDFlyPawn.h"
#include "FDCourseInfo.h"
#include "FDMinimap.h"
#include "FDTravelPoint.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "Widgets/Layout/SBox.h"

namespace
{
	constexpr int32 DebugMessageKey = 7104;
	constexpr int32 HintMessageKey = 7103;  // FDBikePawn の案内と同じ行に出す

	// 関節の位置 (tools/vehicle/build_walker.py と同じ値)
	constexpr float LegLengthCm = 90.f;  // 股関節から足の裏まで
	constexpr float KneeDropCm = 43.f;   // 股関節から膝まで
	constexpr float ArmLengthCm = 60.f;
	constexpr float ElbowDropCm = 29.f;  // 肩から肘まで
	constexpr float HipZCm = 90.f;       // 足の裏からの高さ
	constexpr float HipYCm = 10.f;
	constexpr float ShoulderZCm = 146.f;
	constexpr float ShoulderYCm = 22.f;

	TSoftObjectPtr<UStaticMesh> FigureMesh(const TCHAR* Name)
	{
		return TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(FString::Printf(TEXT("/Game/FukuokaDrive/Vehicle/%s/StaticMeshes/%s.%s"), Name, Name, Name)));
	}

	// 見回し: マウスは動かした量 (度 / 入力の値)、ゲームパッドのスティックは速さ (度/秒)
	constexpr float MouseLookScale = 2.5f;
	constexpr float StickLookRateDeg = 150.f;
	constexpr float MinPitchDeg = -70.f;
	constexpr float MaxPitchDeg = 40.f;

	// エンジン付属の基本形状のマテリアル。Color で色を変えられる
	const TCHAR* const ShapeColorParam = TEXT("Color");
}

AFDWalkerCharacter::AFDWalkerCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessAI = EAutoPossessAI::Disabled;

	GetCapsuleComponent()->InitCapsuleSize(34.f, CapsuleHalfHeightCm);

	// 体は進む向きへ回し、カメラはマウスで自由に回す
	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;
	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.f, 540.f, 0.f);
	Move->MaxWalkSpeed = WalkSpeedCms;
	Move->BrakingDecelerationWalking = 1600.f;
	Move->JumpZVelocity = 420.f;
	Move->AirControl = 0.35f;

	SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArm"));
	SpringArm->SetupAttachment(GetCapsuleComponent());
	SpringArm->TargetArmLength = 320.f;
	SpringArm->SocketOffset = FVector(0.f, 0.f, 50.f);
	SpringArm->bUsePawnControlRotation = true;
	SpringArm->bEnableCameraLag = true;
	SpringArm->CameraLagSpeed = 12.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SpringArm, USpringArmComponent::SocketName);
	Camera->SetFieldOfView(80.f);

	// 人形 (基本形状はどれも中心が原点で、円柱と球は直径 100cm、立方体は一辺 100cm)
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMaterial(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	UStaticMesh* Cylinder = CylinderMesh.Object;
	UStaticMesh* Sphere = SphereMesh.Object;
	UStaticMesh* Cube = CubeMesh.Object;
	ShapeMaterial = BasicMaterial.Object;

	Figure = CreateDefaultSubobject<USceneComponent>(TEXT("Figure"));
	Figure->SetupAttachment(GetCapsuleComponent());
	Figure->SetRelativeLocation(FVector(0.f, 0.f, -CapsuleHalfHeightCm));

	BodyMeshAsset = FigureMesh(TEXT("SM_FD_WalkerBody"));
	UpperArmMeshAsset = FigureMesh(TEXT("SM_FD_WalkerUpperArm"));
	ForearmMeshAsset = FigureMesh(TEXT("SM_FD_WalkerForearm"));
	ThighMeshAsset = FigureMesh(TEXT("SM_FD_WalkerThigh"));
	ShinMeshAsset = FigureMesh(TEXT("SM_FD_WalkerShin"));

	auto MakeJoint = [this](const TCHAR* Name, USceneComponent* Parent, const FVector& Location)
	{
		USceneComponent* Joint = CreateDefaultSubobject<USceneComponent>(Name);
		Joint->SetupAttachment(Parent);
		Joint->SetRelativeLocation(Location);
		return Joint;
	};
	LeftHip = MakeJoint(TEXT("LeftHip"), Figure, FVector(0.f, -HipYCm, HipZCm));
	RightHip = MakeJoint(TEXT("RightHip"), Figure, FVector(0.f, HipYCm, HipZCm));
	LeftKnee = MakeJoint(TEXT("LeftKnee"), LeftHip, FVector(0.f, 0.f, -KneeDropCm));
	RightKnee = MakeJoint(TEXT("RightKnee"), RightHip, FVector(0.f, 0.f, -KneeDropCm));
	LeftShoulder = MakeJoint(TEXT("LeftShoulder"), Figure, FVector(0.f, -ShoulderYCm, ShoulderZCm));
	RightShoulder = MakeJoint(TEXT("RightShoulder"), Figure, FVector(0.f, ShoulderYCm, ShoulderZCm));
	LeftElbow = MakeJoint(TEXT("LeftElbow"), LeftShoulder, FVector(0.f, 0.f, -ElbowDropCm));
	RightElbow = MakeJoint(TEXT("RightElbow"), RightShoulder, FVector(0.f, 0.f, -ElbowDropCm));

	// 取り込んだメッシュを置く部品 (メッシュは BeginPlay で入れる)。右側のメッシュを左右反転して左に使う
	MakeFigureMesh(Figure, TEXT("BodyMesh"), false);
	MakeFigureMesh(LeftShoulder, TEXT("LeftUpperArmMesh"), true);
	MakeFigureMesh(RightShoulder, TEXT("RightUpperArmMesh"), false);
	MakeFigureMesh(LeftElbow, TEXT("LeftForearmMesh"), true);
	MakeFigureMesh(RightElbow, TEXT("RightForearmMesh"), false);
	MakeFigureMesh(LeftHip, TEXT("LeftThighMesh"), true);
	MakeFigureMesh(RightHip, TEXT("RightThighMesh"), false);
	MakeFigureMesh(LeftKnee, TEXT("LeftShinMesh"), true);
	MakeFigureMesh(RightKnee, TEXT("RightShinMesh"), false);

	// メッシュがまだ取り込まれていないときの仮の人形 (基本形状はどれも中心が原点で、円柱と球は直径 100cm、立方体は一辺 100cm)
	MakePart(Figure, TEXT("Torso"), Cube, FVector(0.f, 0.f, 120.f), FVector(0.22f, 0.38f, 0.60f), EPartColor::Jacket);
	MakePart(Figure, TEXT("Neck"), Cylinder, FVector(0.f, 0.f, 152.f), FVector(0.10f, 0.10f, 0.08f), EPartColor::Skin);
	MakePart(Figure, TEXT("Head"), Sphere, FVector(0.f, 0.f, 164.f), FVector(0.21f, 0.20f, 0.23f), EPartColor::Skin);
	MakePart(Figure, TEXT("Hair"), Sphere, FVector(-1.5f, 0.f, 168.f), FVector(0.225f, 0.215f, 0.18f), EPartColor::Hair);

	const float ShinCm = LegLengthCm - KneeDropCm - 4.f;
	const FVector ThighScale(0.15f, 0.15f, KneeDropCm / 100.f);
	const FVector ShinScale(0.12f, 0.12f, ShinCm / 100.f);
	const FVector ShoeScale(0.27f, 0.11f, 0.07f);
	for (int32 Side = 0; Side < 2; ++Side)
	{
		USceneComponent* Hip = Side ? RightHip.Get() : LeftHip.Get();
		USceneComponent* Knee = Side ? RightKnee.Get() : LeftKnee.Get();
		USceneComponent* Shoulder = Side ? RightShoulder.Get() : LeftShoulder.Get();
		USceneComponent* Elbow = Side ? RightElbow.Get() : LeftElbow.Get();
		const TCHAR* Prefix = Side ? TEXT("Right") : TEXT("Left");
		auto Name = [Prefix](const TCHAR* Part) { return FName(*FString::Printf(TEXT("%s%s"), Prefix, Part)); };
		MakePart(Hip, *Name(TEXT("Thigh")).ToString(), Cylinder, FVector(0.f, 0.f, -KneeDropCm * 0.5f), ThighScale, EPartColor::Pants);
		MakePart(Knee, *Name(TEXT("Shin")).ToString(), Cylinder, FVector(0.f, 0.f, -ShinCm * 0.5f), ShinScale, EPartColor::Pants);
		MakePart(Knee, *Name(TEXT("Shoe")).ToString(), Cube, FVector(5.f, 0.f, KneeDropCm - LegLengthCm + 3.5f), ShoeScale, EPartColor::Shoe);
		MakePart(Shoulder, *Name(TEXT("UpperArm")).ToString(), Cylinder, FVector(0.f, 0.f, -ElbowDropCm * 0.5f),
		         FVector(0.11f, 0.11f, ElbowDropCm / 100.f), EPartColor::Jacket);
		MakePart(Elbow, *Name(TEXT("Forearm")).ToString(), Cylinder, FVector(0.f, 0.f, -(ArmLengthCm - ElbowDropCm) * 0.5f),
		         FVector(0.10f, 0.10f, (ArmLengthCm - ElbowDropCm) / 100.f), EPartColor::Jacket);
		MakePart(Elbow, *Name(TEXT("Hand")).ToString(), Sphere, FVector(0.f, 0.f, ElbowDropCm - ArmLengthCm - 3.f),
		         FVector(0.10f, 0.08f, 0.11f), EPartColor::Skin);
	}
}

UStaticMeshComponent* AFDWalkerCharacter::MakeFigureMesh(USceneComponent* Parent, const TCHAR* Name, bool bMirror)
{
	UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	Part->SetupAttachment(Parent);
	Part->SetRelativeScale3D(FVector(1.f, bMirror ? -1.f : 1.f, 1.f));
	Part->SetCollisionProfileName(TEXT("NoCollision"));
	Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Part->SetGenerateOverlapEvents(false);
	Part->SetVisibility(false);
	FigureMeshes.Add(Part);
	return Part;
}

UStaticMeshComponent* AFDWalkerCharacter::MakePart(USceneComponent* Parent, const TCHAR* Name, UStaticMesh* PartMesh,
                                                   const FVector& Location, const FVector& Scale, EPartColor Color)
{
	UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	Part->SetupAttachment(Parent);
	Part->SetStaticMesh(PartMesh);
	Part->SetRelativeLocation(Location);
	Part->SetRelativeScale3D(Scale);
	// 見た目だけ。当たり判定はカプセルで取る
	Part->SetCollisionProfileName(TEXT("NoCollision"));
	Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Part->SetGenerateOverlapEvents(false);
	PartMeshes.Add(Part);
	PartColors.Add(Color);
	FallbackParts.Add(Part);
	return Part;
}

FLinearColor AFDWalkerCharacter::GetPartColor(EPartColor Color) const
{
	switch (Color)
	{
	case EPartColor::Skin: return SkinColor;
	case EPartColor::Hair: return HairColor;
	case EPartColor::Jacket: return JacketColor;
	case EPartColor::Pants: return PantsColor;
	case EPartColor::Shoe: return ShoeColor;
	}
	return FLinearColor::White;
}

void AFDWalkerCharacter::ApplyFigureMeshes()
{
	UStaticMesh* Body = BodyMeshAsset.LoadSynchronous();
	UStaticMesh* UpperArm = UpperArmMeshAsset.LoadSynchronous();
	UStaticMesh* Forearm = ForearmMeshAsset.LoadSynchronous();
	UStaticMesh* Thigh = ThighMeshAsset.LoadSynchronous();
	UStaticMesh* Shin = ShinMeshAsset.LoadSynchronous();
	bUsingFigureMeshes = Body && UpperArm && Forearm && Thigh && Shin;
	if (!bUsingFigureMeshes)
	{
		return;
	}
	// FigureMeshes は コンストラクタで作った順 (胴、上腕 左右、前腕 左右、太もも 左右、すね 左右)
	UStaticMesh* const Meshes[] = {Body, UpperArm, UpperArm, Forearm, Forearm, Thigh, Thigh, Shin, Shin};
	for (int32 i = 0; i < FigureMeshes.Num() && i < UE_ARRAY_COUNT(Meshes); ++i)
	{
		if (UStaticMeshComponent* Part = FigureMeshes[i])
		{
			Part->SetStaticMesh(Meshes[i]);
			Part->SetVisibility(true);
		}
	}
	for (UStaticMeshComponent* Part : FallbackParts)
	{
		if (Part)
		{
			Part->SetVisibility(false);
		}
	}
}

void AFDWalkerCharacter::ApplyColors()
{
	for (int32 i = 0; i < PartMeshes.Num() && i < PartColors.Num(); ++i)
	{
		if (UStaticMeshComponent* Part = PartMeshes[i])
		{
			if (UMaterialInstanceDynamic* Material = Part->CreateDynamicMaterialInstance(0, ShapeMaterial))
			{
				Material->SetVectorParameterValue(FName(ShapeColorParam), GetPartColor(PartColors[i]));
			}
		}
	}
	if (!bUsingFigureMeshes)
	{
		return;
	}
	// 取り込んだメッシュは、スロット名 (glTF のマテリアル名 FD_WK_Skin など) で色を決める
	static const TPair<const TCHAR*, EPartColor> SlotColors[] = {
		{TEXT("Skin"), EPartColor::Skin}, {TEXT("Hair"), EPartColor::Hair}, {TEXT("Jacket"), EPartColor::Jacket},
		{TEXT("Pants"), EPartColor::Pants}, {TEXT("Shoe"), EPartColor::Shoe}};
	for (UStaticMeshComponent* Part : FigureMeshes)
	{
		if (!Part)
		{
			continue;
		}
		const TArray<FName> Slots = Part->GetMaterialSlotNames();
		for (int32 Slot = 0; Slot < Part->GetNumMaterials(); ++Slot)
		{
			const FString SlotName = Slots.IsValidIndex(Slot) ? Slots[Slot].ToString() : FString();
			const UMaterialInterface* Current = Part->GetMaterial(Slot);
			const FString MaterialName = Current ? Current->GetName() : FString();
			for (const TPair<const TCHAR*, EPartColor>& Entry : SlotColors)
			{
				if (SlotName.Contains(Entry.Key) || MaterialName.Contains(Entry.Key))
				{
					if (UMaterialInstanceDynamic* Material = Part->CreateDynamicMaterialInstance(Slot, ShapeMaterial))
					{
						Material->SetVectorParameterValue(FName(ShapeColorParam), GetPartColor(Entry.Value));
					}
					break;
				}
			}
		}
	}
}

void AFDWalkerCharacter::BeginPlay()
{
	Super::BeginPlay();
	ApplyFigureMeshes();
	ApplyColors();
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeedCms;
	LastSafeLocation = GetActorLocation();
}

void AFDWalkerCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Menu.Close();
	HideMinimap();
	Super::EndPlay(EndPlayReason);
}

// ---------------------------------------------------------------- 入力

void AFDWalkerCharacter::CreateInputAssets()
{
	if (MappingContext)
	{
		return;
	}

	// 入力アセットはコードで作る (FDBikePawn と同じ)
	auto MakeAction = [this](const TCHAR* Name, EInputActionValueType Type)
	{
		UInputAction* Action = NewObject<UInputAction>(this, Name);
		Action->ValueType = Type;
		return Action;
	};
	MoveAction = MakeAction(TEXT("IA_WalkMove"), EInputActionValueType::Axis2D);
	LookAction = MakeAction(TEXT("IA_WalkLook"), EInputActionValueType::Axis2D);
	LookStickAction = MakeAction(TEXT("IA_WalkLookStick"), EInputActionValueType::Axis2D);
	RunAction = MakeAction(TEXT("IA_WalkRun"), EInputActionValueType::Boolean);
	JumpAction = MakeAction(TEXT("IA_WalkJump"), EInputActionValueType::Boolean);
	RideAction = MakeAction(TEXT("IA_Ride"), EInputActionValueType::Boolean);
	ReturnAction = MakeAction(TEXT("IA_ReturnToBike"), EInputActionValueType::Boolean);
	TravelMenuAction = MakeAction(TEXT("IA_WalkTravelMenu"), EInputActionValueType::Boolean);
	FlyAction = MakeAction(TEXT("IA_WalkFly"), EInputActionValueType::Boolean);

	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_Walker"));

	// 移動は X = 右、Y = 前。キーは1軸の値なので、前後のキーは Y へ入れ替え、後ろと左は符号を反転する
	auto MapMove = [this](const FKey& Key, bool bForwardAxis, bool bNegate)
	{
		FEnhancedActionKeyMapping& Mapping = MappingContext->MapKey(MoveAction, Key);
		if (bForwardAxis)
		{
			UInputModifierSwizzleAxis* Swizzle = NewObject<UInputModifierSwizzleAxis>(MappingContext);
			Swizzle->Order = EInputAxisSwizzle::YXZ;
			Mapping.Modifiers.Add(Swizzle);
		}
		if (bNegate)
		{
			Mapping.Modifiers.Add(NewObject<UInputModifierNegate>(MappingContext));
		}
	};
	MapMove(EKeys::W, true, false);
	MapMove(EKeys::Up, true, false);
	MapMove(EKeys::S, true, true);
	MapMove(EKeys::Down, true, true);
	MapMove(EKeys::D, false, false);
	MapMove(EKeys::Right, false, false);
	MapMove(EKeys::A, false, true);
	MapMove(EKeys::Left, false, true);
	MappingContext->MapKey(MoveAction, EKeys::Gamepad_Left2D).Modifiers.Add(NewObject<UInputModifierDeadZone>(MappingContext));

	// マウスは動かした量、スティックは傾けた量 (速さ) なので別にする
	MappingContext->MapKey(LookAction, EKeys::Mouse2D);
	MappingContext->MapKey(LookStickAction, EKeys::Gamepad_Right2D).Modifiers.Add(NewObject<UInputModifierDeadZone>(MappingContext));

	MappingContext->MapKey(RunAction, EKeys::LeftShift);
	MappingContext->MapKey(RunAction, EKeys::RightShift);
	MappingContext->MapKey(RunAction, EKeys::Gamepad_LeftThumbstick);

	MappingContext->MapKey(JumpAction, EKeys::SpaceBar);
	MappingContext->MapKey(JumpAction, EKeys::Gamepad_FaceButton_Bottom);

	MappingContext->MapKey(RideAction, EKeys::E);
	MappingContext->MapKey(RideAction, EKeys::Gamepad_FaceButton_Left);

	MappingContext->MapKey(ReturnAction, EKeys::R);
	MappingContext->MapKey(ReturnAction, EKeys::Gamepad_FaceButton_Top);

	MappingContext->MapKey(TravelMenuAction, EKeys::F);
	MappingContext->MapKey(TravelMenuAction, EKeys::Gamepad_Special_Left);

	MappingContext->MapKey(FlyAction, EKeys::B);
	MappingContext->MapKey(FlyAction, EKeys::Gamepad_DPad_Up);
}

void AFDWalkerCharacter::PawnClientRestart()
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

void AFDWalkerCharacter::UnPossessed()
{
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
	if (GEngine)
	{
		GEngine->RemoveOnScreenDebugMessage(DebugMessageKey);
	}
}

void AFDWalkerCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	CreateInputAssets();
	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!Input)
	{
		UE_LOG(LogTemp, Error, TEXT("FDWalkerCharacter: Enhanced Input が有効になっていません"));
		return;
	}

	Input->BindAction(MoveAction, ETriggerEvent::Triggered, this, &AFDWalkerCharacter::OnMove);
	Input->BindActionValueLambda(LookAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V)
	{
		Look(V.Get<FVector2D>() * MouseLookScale);
	});
	Input->BindActionValueLambda(LookStickAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V)
	{
		Look(V.Get<FVector2D>() * StickLookRateDeg * GetWorld()->GetDeltaSeconds());
	});
	Input->BindActionValueLambda(RunAction, ETriggerEvent::Started, [this](const FInputActionValue&)
	{
		bRunning = true;
		GetCharacterMovement()->MaxWalkSpeed = RunSpeedCms;
	});
	Input->BindActionValueLambda(RunAction, ETriggerEvent::Completed, [this](const FInputActionValue&)
	{
		bRunning = false;
		GetCharacterMovement()->MaxWalkSpeed = WalkSpeedCms;
	});
	Input->BindActionValueLambda(JumpAction, ETriggerEvent::Started, [this](const FInputActionValue&) { Jump(); });
	Input->BindActionValueLambda(JumpAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { StopJumping(); });
	Input->BindActionValueLambda(RideAction, ETriggerEvent::Started, [this](const FInputActionValue&) { GetOn(); });
	Input->BindActionValueLambda(ReturnAction, ETriggerEvent::Started, [this](const FInputActionValue&) { ReturnToBike(); });
	Input->BindActionValueLambda(TravelMenuAction, ETriggerEvent::Started, [this](const FInputActionValue&) { ToggleTravelMenu(); });
	Input->BindActionValueLambda(FlyAction, ETriggerEvent::Started, [this](const FInputActionValue&) { StartFlying(); });
}

void AFDWalkerCharacter::OnMove(const FInputActionValue& Value)
{
	const FVector2D Axis = Value.Get<FVector2D>();
	const FRotator Facing(0.f, GetControlRotation().Yaw, 0.f);
	const FRotationMatrix Basis(Facing);
	AddMovementInput(Basis.GetUnitAxis(EAxis::X), Axis.Y);
	AddMovementInput(Basis.GetUnitAxis(EAxis::Y), Axis.X);
}

void AFDWalkerCharacter::Look(const FVector2D& DeltaDeg)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return;
	}
	// 右へ動かすと右を、上へ動かすと上を見る (AddControllerPitchInput の古い倍率 -2.5 は通さない)
	FRotator Rotation = PC->GetControlRotation();
	Rotation.Yaw = FRotator::NormalizeAxis(Rotation.Yaw + DeltaDeg.X);
	Rotation.Pitch = FMath::Clamp(FRotator::NormalizeAxis(Rotation.Pitch + DeltaDeg.Y), MinPitchDeg, MaxPitchDeg);
	Rotation.Roll = 0.f;
	PC->SetControlRotation(Rotation);
}

// ---------------------------------------------------------------- 乗り降り・ファストトラベル

float AFDWalkerCharacter::DistanceToBikeCm() const
{
	return Bike ? FVector::Dist2D(Bike->GetActorLocation(), GetActorLocation()) : TNumericLimits<float>::Max();
}

void AFDWalkerCharacter::GetOn()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC || !Bike)
	{
		return;
	}
	if (DistanceToBikeCm() > RideReachCm)
	{
		if (GEngine)
		{
			// デバッグ表示のフォントは日本語を出せない
			GEngine->AddOnScreenDebugMessage(HintMessageKey, 2.f, FColor::Yellow, TEXT("Walk up to the bike to ride (R = back to the bike)"));
		}
		return;
	}
	AFDBikePawn* Ride = Bike;
	PC->Possess(Ride);
	Destroy();
}

void AFDWalkerCharacter::StartFlying()
{
	Menu.Close();
	GetCharacterMovement()->StopMovementImmediately();
	AFDFlyPawn::StartFrom(this);
}

void AFDWalkerCharacter::ReturnToBike()
{
	if (!Bike)
	{
		return;
	}
	const FTransform Stand = Bike->GetDismountTransform();
	SetActorLocationAndRotation(Stand.GetLocation() + FVector(0.f, 0.f, StandHeightCm), Stand.Rotator(), false, nullptr, ETeleportType::TeleportPhysics);
	GetCharacterMovement()->StopMovementImmediately();
	LastSafeLocation = GetActorLocation();
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->SetControlRotation(FRotator(-12.f, Stand.Rotator().Yaw, 0.f));
	}
}

void AFDWalkerCharacter::ToggleTravelMenu()
{
	if (Menu.IsOpen())
	{
		Menu.Close();
		return;
	}
	Menu.OpenTravel(Cast<APlayerController>(GetController()), [this](const AFDTravelPoint* Point) { TravelTo(Point); });
}

void AFDWalkerCharacter::TravelTo(const AFDTravelPoint* Point)
{
	if (!Point)
	{
		return;
	}
	if (Bike)
	{
		// バイクを行き先の道路に下ろし、その横に立つ
		Bike->TravelTo(Point);
		ReturnToBike();
		return;
	}
	SetActorLocationAndRotation(Point->GetActorLocation() + FVector(0.f, 0.f, StandHeightCm), FRotator(0.f, Point->GetActorRotation().Yaw, 0.f),
	                            false, nullptr, ETeleportType::TeleportPhysics);
	GetCharacterMovement()->StopMovementImmediately();
	LastSafeLocation = GetActorLocation();
}

// ---------------------------------------------------------------- ミニマップ

void AFDWalkerCharacter::ShowMinimap()
{
	UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	// 地図の画像と大きさはバイクの設定を使う
	if (Minimap.IsValid() || !Bike || !Bike->bShowMinimap || !Viewport || !IsLocallyControlled())
	{
		return;
	}
	LoadedMinimapTexture = Bike->MinimapTexture.LoadSynchronous();
	const AFDCourseInfo* Course = AFDCourseInfo::Find(GetWorld());
	const float GridRotationDeg = Course ? Course->GridRotationDeg : 0.f;
	TArray<FVector2D> Markers;
	for (const AFDTravelPoint* Point : FFDMenu::GetTravelPoints(GetWorld()))
	{
		Markers.Add(FVector2D(Point->GetActorLocation()));
	}
	Minimap = SNew(SBox).HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(FMargin(0.f, 0.f, 32.f, 32.f))
	[
		SNew(SFDMinimap)
		.Player(this)
		.ParkedBike(Bike.Get())
		.MapTexture(LoadedMinimapTexture)
		.MapMin(Bike->MinimapWorldMin)
		.MapMax(Bike->MinimapWorldMax)
		.Markers(Markers)
		.Diameter(Bike->MinimapDiameter)
		.RadiusSlowM(Bike->MinimapRadiusSlowM * 0.5f)  // 歩くときは近くを大きく
		.RadiusFastM(Bike->MinimapRadiusSlowM)
		.GridRotationDeg(GridRotationDeg)
	];
	Viewport->AddViewportWidgetContent(Minimap.ToSharedRef(), 5);
}

void AFDWalkerCharacter::HideMinimap()
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

// ---------------------------------------------------------------- 毎フレーム

void AFDWalkerCharacter::KeepOutOfSea()
{
	const FVector Location = GetActorLocation();
	const float FootZ = Location.Z - GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	if (FootZ < -MaxWadeDepthCm)
	{
		// 波打ち際より先へは行かない (海に入った、または地面の外へ落ちた)
		SetActorLocation(LastSafeLocation, false, nullptr, ETeleportType::TeleportPhysics);
		GetCharacterMovement()->StopMovementImmediately();
		return;
	}
	if (GetCharacterMovement()->IsMovingOnGround())
	{
		LastSafeLocation = Location;
	}
}

void AFDWalkerCharacter::UpdateLimbs(float DeltaSeconds)
{
	const float Dt = FMath::Min(DeltaSeconds, 0.05f);
	const float Speed = GetVelocity().Size2D();
	const bool bGround = GetCharacterMovement()->IsMovingOnGround();
	const float RunT = FMath::Clamp((Speed - WalkSpeedCms) / FMath::Max(RunSpeedCms - WalkSpeedCms, 1.f), 0.f, 1.f);

	// 一歩 (片足を前に出す) で進む距離に合わせて振る。走るほど大きく振る
	const float StepCm = FMath::Lerp(70.f, 130.f, RunT);
	const float TargetSwing = bGround ? FMath::Min(Speed / FMath::Max(WalkSpeedCms, 1.f), 1.f) * 25.f + RunT * 20.f : 18.f;
	SwingDeg = FMath::FInterpTo(SwingDeg, TargetSwing, Dt, 8.f);
	if (bGround)
	{
		StridePhase = FMath::Fmod(StridePhase + Speed * Dt / StepCm * UE_PI, UE_TWO_PI);
	}

	// 股関節と肩: 前後に振る (正の Pitch で足先・手先が前へ出る)
	const float Swing = FMath::Sin(StridePhase) * SwingDeg;
	LeftHip->SetRelativeRotation(FRotator(Swing, 0.f, 0.f));
	RightHip->SetRelativeRotation(FRotator(-Swing, 0.f, 0.f));
	LeftShoulder->SetRelativeRotation(FRotator(-Swing * 0.8f, 0.f, 0.f));
	RightShoulder->SetRelativeRotation(FRotator(Swing * 0.8f, 0.f, 0.f));

	// 膝: 脚を前へ振り出している間 (振れ角が増えている間) だけ曲げる。走るほど深く曲げる。空中では軽く曲げたまま
	const float KneeAmp = bGround ? SwingDeg * 1.3f + RunT * 30.f : 35.f;
	const float LeftForward = FMath::Max(0.f, FMath::Cos(StridePhase));
	const float RightForward = FMath::Max(0.f, -FMath::Cos(StridePhase));
	LeftKnee->SetRelativeRotation(FRotator(-(4.f + KneeAmp * LeftForward), 0.f, 0.f));
	RightKnee->SetRelativeRotation(FRotator(-(4.f + KneeAmp * RightForward), 0.f, 0.f));

	// 肘: いつも少し曲げ、走ると大きく曲げる。腕を前へ振ったときに少し余計に曲げる
	const float ElbowBase = 12.f + RunT * 65.f;
	LeftElbow->SetRelativeRotation(FRotator(ElbowBase + FMath::Max(0.f, -Swing) * 0.4f, 0.f, 0.f));
	RightElbow->SetRelativeRotation(FRotator(ElbowBase + FMath::Max(0.f, Swing) * 0.4f, 0.f, 0.f));

	// 足を開いた分だけ腰が下がる (膝を曲げた脚は短くなるので、伸ばしている方の脚で決める)
	const float Drop = LegLengthCm * (1.f - FMath::Cos(FMath::DegreesToRadians(Swing)));
	Figure->SetRelativeLocation(FVector(0.f, 0.f, -CapsuleHalfHeightCm - Drop));
}

void AFDWalkerCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	KeepOutOfSea();
	UpdateLimbs(DeltaSeconds);

	if (bShowDebugText && IsLocallyControlled() && GEngine)
	{
		const float Dist = DistanceToBikeCm();
		const FString Ride = !Bike ? FString()
		                   : Dist <= RideReachCm ? FString(TEXT("E = ride"))
		                   : FString::Printf(TEXT("bike %.0f m"), Dist / 100.f);
		GEngine->AddOnScreenDebugMessage(
			DebugMessageKey, 0.f, FColor::White,
			FString::Printf(TEXT("%3.1f km/h  %s   [W/S/A/D, mouse = look, Shift = run, Space = jump, R = back to bike, F = travel, B = fly]"),
			                GetVelocity().Size2D() * 0.036f, *Ride));
	}
}
