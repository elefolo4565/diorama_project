#include "FDNightLights.h"

#include "Components/SpotLightComponent.h"
#include "Engine/World.h"

AFDNightLights::AFDNightLights()
{
	PrimaryActorTick.bCanEverTick = false;

	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	SetRootComponent(Root);
}

void AFDNightLights::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	if (!GetWorld() || !GetWorld()->IsGameWorld())
	{
		OnAmount = EditorOnAmount;
	}
	BuildLights();
}

void AFDNightLights::BeginPlay()
{
	Super::BeginPlay();
	// プレイ用に複製したレベルには、保存しない光源は付いてこないので作り直す。
	// FDTimeOfDay の BeginPlay が先に SetOnAmount していれば、その点き具合で作る
	if (Spots.Num() != Lights.Num())
	{
		BuildLights();
	}
}

void AFDNightLights::BuildLights()
{
	for (USpotLightComponent* Spot : Spots)
	{
		if (Spot)
		{
			Spot->DestroyComponent();
		}
	}
	Spots.Reset();

	for (const FTransform& T : Lights)
	{
		USpotLightComponent* Spot = NewObject<USpotLightComponent>(this, NAME_None, RF_Transient);
		Spot->SetMobility(EComponentMobility::Movable);
		Spot->SetupAttachment(GetRootComponent());
		Spot->SetIntensityUnits(ELightUnits::Lumens);
		Spot->SetIntensity(0.f);
		Spot->bUseTemperature = true;
		Spot->Temperature = Temperature;
		Spot->SetAttenuationRadius(AttenuationRadius);
		Spot->SetInnerConeAngle(InnerConeAngle);
		Spot->SetOuterConeAngle(OuterConeAngle);
		Spot->SetSourceRadius(8.f);
		Spot->SetSoftSourceRadius(15.f);
		Spot->SetCastShadows(bCastShadows);
		Spot->SetVolumetricScatteringIntensity(VolumetricScattering);
		Spot->MaxDrawDistance = MaxDrawDistance;
		Spot->MaxDistanceFadeRange = MaxDrawDistance * 0.2f;
		Spot->RegisterComponent();
		Spot->SetWorldTransform(T);
		Spots.Add(Spot);
	}
	ApplyOnAmount();
}

void AFDNightLights::SetOnAmount(float Amount)
{
	Amount = FMath::Clamp(Amount, 0.f, 1.f);
	if (FMath::IsNearlyEqual(Amount, OnAmount, 0.001f) && FMath::IsNearlyEqual(Amount, AppliedAmount, 0.001f))
	{
		return;
	}
	OnAmount = Amount;
	ApplyOnAmount();
}

void AFDNightLights::ApplyOnAmount()
{
	AppliedAmount = OnAmount;
	const bool bOn = OnAmount > 0.001f;
	for (USpotLightComponent* Spot : Spots)
	{
		if (Spot)
		{
			Spot->SetIntensity(Intensity * OnAmount);
			Spot->SetVisibility(bOn);
		}
	}
}
