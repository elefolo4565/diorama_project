#include "FDFlyPawn.h"
#include "Camera/CameraComponent.h"
#include "Engine/Engine.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"

namespace
{
	constexpr int32 DebugMessageKey = 7105;
	/** 地面を探すときに上と下へ引く線の長さ (cm) */
	constexpr float GroundTraceUpCm = 200000.f;
	constexpr float GroundTraceDownCm = 200000.f;
}

AFDFlyPawn::AFDFlyPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessAI = EAutoPossessAI::Disabled;
	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);
	Camera->bUsePawnControlRotation = true;
	Camera->SetFieldOfView(80.f);
}

AFDFlyPawn* AFDFlyPawn::StartFrom(APawn* From)
{
	APlayerController* PC = From ? Cast<APlayerController>(From->GetController()) : nullptr;
	UWorld* World = From ? From->GetWorld() : nullptr;
	if (!PC || !World)
	{
		return nullptr;
	}
	// いま見えているカメラの位置と向きから飛び立つ
	FVector ViewLocation;
	FRotator ViewRotation;
	PC->GetPlayerViewPoint(ViewLocation, ViewRotation);

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AFDFlyPawn* Fly = World->SpawnActor<AFDFlyPawn>(AFDFlyPawn::StaticClass(), ViewLocation, FRotator::ZeroRotator, Params);
	if (!Fly)
	{
		return nullptr;
	}
	Fly->ReturnPawn = From;
	PC->Possess(Fly);
	PC->SetControlRotation(FRotator(ViewRotation.Pitch, ViewRotation.Yaw, 0.f));
	return Fly;
}

// ---------------------------------------------------------------- 入力

void AFDFlyPawn::CreateInputAssets()
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
	MoveAction = MakeAction(TEXT("IA_FlyMove"), EInputActionValueType::Axis2D);
	UpDownAction = MakeAction(TEXT("IA_FlyUpDown"), EInputActionValueType::Axis1D);
	LookAction = MakeAction(TEXT("IA_FlyLook"), EInputActionValueType::Axis2D);
	LookStickAction = MakeAction(TEXT("IA_FlyLookStick"), EInputActionValueType::Axis2D);
	BoostAction = MakeAction(TEXT("IA_FlyBoost"), EInputActionValueType::Boolean);
	SpeedAction = MakeAction(TEXT("IA_FlySpeed"), EInputActionValueType::Axis1D);
	ReturnAction = MakeAction(TEXT("IA_FlyReturn"), EInputActionValueType::Boolean);

	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_Fly"));

	// 移動は X = 右、Y = 前 (FDWalkerCharacter と同じ)
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

	auto MapNegated = [this](UInputAction* Action, const FKey& Key)
	{
		MappingContext->MapKey(Action, Key).Modifiers.Add(NewObject<UInputModifierNegate>(MappingContext));
	};
	MappingContext->MapKey(UpDownAction, EKeys::E);
	MappingContext->MapKey(UpDownAction, EKeys::SpaceBar);
	MappingContext->MapKey(UpDownAction, EKeys::Gamepad_RightTriggerAxis);
	MapNegated(UpDownAction, EKeys::Q);
	MapNegated(UpDownAction, EKeys::LeftControl);
	MapNegated(UpDownAction, EKeys::Gamepad_LeftTriggerAxis);

	MappingContext->MapKey(LookAction, EKeys::Mouse2D);
	MappingContext->MapKey(LookStickAction, EKeys::Gamepad_Right2D).Modifiers.Add(NewObject<UInputModifierDeadZone>(MappingContext));

	MappingContext->MapKey(BoostAction, EKeys::LeftShift);
	MappingContext->MapKey(BoostAction, EKeys::RightShift);
	MappingContext->MapKey(BoostAction, EKeys::Gamepad_LeftThumbstick);

	MappingContext->MapKey(SpeedAction, EKeys::MouseWheelAxis);
	MappingContext->MapKey(SpeedAction, EKeys::Gamepad_RightShoulder);
	MapNegated(SpeedAction, EKeys::Gamepad_LeftShoulder);

	MappingContext->MapKey(ReturnAction, EKeys::B);
	MappingContext->MapKey(ReturnAction, EKeys::Gamepad_DPad_Up);
}

void AFDFlyPawn::PawnClientRestart()
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
}

void AFDFlyPawn::UnPossessed()
{
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
				ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			Subsystem->RemoveMappingContext(MappingContext);
		}
	}
	Super::UnPossessed();
	if (GEngine)
	{
		GEngine->RemoveOnScreenDebugMessage(DebugMessageKey);
	}
}

void AFDFlyPawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	CreateInputAssets();
	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!Input)
	{
		UE_LOG(LogTemp, Error, TEXT("FDFlyPawn: Enhanced Input が有効になっていません"));
		return;
	}

	Input->BindActionValueLambda(MoveAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V) { MoveInput = V.Get<FVector2D>(); });
	Input->BindActionValueLambda(MoveAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { MoveInput = FVector2D::ZeroVector; });
	Input->BindActionValueLambda(UpDownAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V) { UpDownInput = FMath::Clamp(V.Get<float>(), -1.f, 1.f); });
	Input->BindActionValueLambda(UpDownAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { UpDownInput = 0.f; });
	Input->BindActionValueLambda(LookAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V)
	{
		Look(V.Get<FVector2D>() * MouseLookScale);
	});
	Input->BindActionValueLambda(LookStickAction, ETriggerEvent::Triggered, [this](const FInputActionValue& V)
	{
		Look(V.Get<FVector2D>() * StickLookRateDeg * GetWorld()->GetDeltaSeconds());
	});
	Input->BindActionValueLambda(BoostAction, ETriggerEvent::Started, [this](const FInputActionValue&) { bBoost = true; });
	Input->BindActionValueLambda(BoostAction, ETriggerEvent::Completed, [this](const FInputActionValue&) { bBoost = false; });
	Input->BindActionValueLambda(SpeedAction, ETriggerEvent::Started, [this](const FInputActionValue& V)
	{
		// ホイール 1 目盛りで 1.25 倍
		const float Step = V.Get<float>() > 0.f ? 1.25f : 0.8f;
		SpeedScale = FMath::Clamp(SpeedScale * Step, SpeedScaleRange.X, SpeedScaleRange.Y);
	});
	Input->BindActionValueLambda(ReturnAction, ETriggerEvent::Started, [this](const FInputActionValue&) { ReturnToGround(); });
}

void AFDFlyPawn::Look(const FVector2D& DeltaDeg)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return;
	}
	FRotator Rotation = PC->GetControlRotation();
	Rotation.Yaw = FRotator::NormalizeAxis(Rotation.Yaw + DeltaDeg.X);
	Rotation.Pitch = FMath::Clamp(FRotator::NormalizeAxis(Rotation.Pitch + DeltaDeg.Y), -89.f, 89.f);
	Rotation.Roll = 0.f;
	PC->SetControlRotation(Rotation);
}

// ---------------------------------------------------------------- 飛ぶ

float AFDFlyPawn::GroundZBelow(const FVector& Location) const
{
	const UWorld* World = GetWorld();
	float GroundZ = 0.f;  // 海面
	if (!World)
	{
		return GroundZ;
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(FDFlyGround), false, this);
	if (ReturnPawn)
	{
		Params.AddIgnoredActor(ReturnPawn);
	}
	const FVector Start(Location.X, Location.Y, Location.Z + GroundTraceUpCm);
	const FVector End(Location.X, Location.Y, Location.Z - GroundTraceDownCm);
	for (int32 Attempt = 0; Attempt < 4; ++Attempt)
	{
		FHitResult Hit;
		if (!World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
		{
			break;
		}
		const AActor* HitActor = Hit.GetActor();
		// 海面 (Water) と、始点が中に入っているもの (遠景の大きな箱など) は地面ではない (FDBikePawn と同じ)
		if (HitActor && (Hit.bStartPenetrating || HitActor->GetClass()->GetName().Contains(TEXT("Water"))))
		{
			Params.AddIgnoredActor(HitActor);
			continue;
		}
		GroundZ = FMath::Max(GroundZ, static_cast<float>(Hit.ImpactPoint.Z));
		break;
	}
	return GroundZ;
}

void AFDFlyPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!IsLocallyControlled())
	{
		return;
	}

	const FRotator View = GetControlRotation();
	const FRotationMatrix Basis(View);
	FVector Wish = Basis.GetUnitAxis(EAxis::X) * MoveInput.Y + Basis.GetUnitAxis(EAxis::Y) * MoveInput.X
		+ FVector::UpVector * UpDownInput;
	if (Wish.SizeSquared() > 1.f)
	{
		Wish.Normalize();
	}
	const float Speed = SpeedCms * SpeedScale * (bBoost ? BoostScale : 1.f);
	Velocity = FMath::VInterpTo(Velocity, Wish * Speed, DeltaSeconds, Responsiveness);

	FVector Next = GetActorLocation() + Velocity * DeltaSeconds;
	const float MinZ = GroundZBelow(Next) + GroundClearanceCm;
	if (Next.Z < MinZ)
	{
		Next.Z = MinZ;
		Velocity.Z = FMath::Max(Velocity.Z, 0.f);
	}
	Next.Z = FMath::Min(Next.Z, MaxAltitudeCm);
	SetActorLocation(Next);

	if (bShowDebugText && GEngine)
	{
		// デバッグ表示のフォントは日本語を出せない
		GEngine->AddOnScreenDebugMessage(DebugMessageKey, 0.f, FColor::Cyan, FString::Printf(
			TEXT("FLY  %.0f km/h  alt %.0f m  (x%.2f)   WASD move  E/Q up/down  Shift fast  wheel speed  B back"),
			Velocity.Size() * 0.036f, GetActorLocation().Z / 100.f, SpeedScale));
	}
}

void AFDFlyPawn::ReturnToGround()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return;
	}
	if (ReturnPawn && !ReturnPawn->IsPendingKillPending())
	{
		const FRotator Facing(-12.f, ReturnPawn->GetActorRotation().Yaw, 0.f);
		PC->Possess(ReturnPawn);
		PC->SetControlRotation(Facing);
		Destroy();
	}
}
