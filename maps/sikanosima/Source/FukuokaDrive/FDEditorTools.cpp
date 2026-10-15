#include "FDEditorTools.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/WorldSettings.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeLayerInfoObject.h"
#include "LandscapeProxy.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "UObject/UnrealType.h"
#include "WorldPartition/WorldPartition.h"

namespace
{
	constexpr int32 QuadsPerSection = 63;
	constexpr int32 SectionsPerComponent = 2;
	const FName RoadLayerName(TEXT("Road"));
}

ALandscape* UFDEditorTools::CreateLandscape(UObject* WorldContextObject, const FString& HeightmapPath, int32 Size,
	FVector CornerLocation, FVector Scale, UMaterialInterface* Material, ULandscapeLayerInfoObject* RoadLayerInfo,
	const FString& RoadWeightPath, const FString& Label)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("[FDEditorTools] ワールドがありません"));
		return nullptr;
	}
	const int32 QuadsPerComponent = QuadsPerSection * SectionsPerComponent;
	if (Size < QuadsPerComponent + 1 || (Size - 1) % QuadsPerComponent != 0)
	{
		UE_LOG(LogTemp, Error, TEXT("[FDEditorTools] 大きさ %d は 126 の倍数 + 1 ではありません"), Size);
		return nullptr;
	}
	const int64 Count = int64(Size) * Size;

	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToArray(Bytes, *HeightmapPath) || Bytes.Num() != Count * 2)
	{
		UE_LOG(LogTemp, Error, TEXT("[FDEditorTools] %s を読めないか、大きさが %d x %d ではありません"), *HeightmapPath, Size, Size);
		return nullptr;
	}
	TArray<uint16> Heights;
	Heights.SetNumUninitialized(Count);
	for (int64 i = 0; i < Count; ++i)
	{
		Heights[i] = uint16(Bytes[2 * i]) | (uint16(Bytes[2 * i + 1]) << 8);
	}
	Bytes.Empty();

	TArray<FLandscapeImportLayerInfo> Layers;
	if (RoadLayerInfo)
	{
		FLandscapeImportLayerInfo Road(RoadLayerName);
		Road.LayerInfo = RoadLayerInfo;
		if (!RoadWeightPath.IsEmpty())
		{
			if (!FFileHelper::LoadFileToArray(Road.LayerData, *RoadWeightPath) || Road.LayerData.Num() != Count)
			{
				UE_LOG(LogTemp, Warning, TEXT("[FDEditorTools] %s を読めません。道路は塗りません"), *RoadWeightPath);
				Road.LayerData.Empty();
			}
		}
		if (Road.LayerData.Num() == 0)
		{
			Road.LayerData.SetNumZeroed(Count);
		}
		Layers.Add(MoveTemp(Road));
	}

	TMap<FGuid, TArray<uint16>> HeightDataPerLayers;
	HeightDataPerLayers.Add(FGuid(), MoveTemp(Heights));
	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayerDataPerLayers;
	MaterialLayerDataPerLayers.Add(FGuid(), Layers);

	ALandscape* Landscape = World->SpawnActor<ALandscape>(CornerLocation, FRotator::ZeroRotator);
	if (!Landscape)
	{
		UE_LOG(LogTemp, Error, TEXT("[FDEditorTools] ランドスケープを置けませんでした"));
		return nullptr;
	}
	Landscape->LandscapeMaterial = Material;
	Landscape->SetActorRelativeScale3D(Scale);
	// 道路の重みは、取り込む前にランドスケープのターゲットレイヤーにしておかないと捨てられる (道が草になる)
	if (RoadLayerInfo)
	{
		Landscape->AddTargetLayer(RoadLayerName, FLandscapeTargetLayerSettings(RoadLayerInfo));
	}
	Landscape->Import(FGuid::NewGuid(), 0, 0, Size - 1, Size - 1, SectionsPerComponent, QuadsPerSection,
		HeightDataPerLayers, *HeightmapPath, MaterialLayerDataPerLayers, ELandscapeImportAlphamapType::Additive,
		TArrayView<const FLandscapeLayer>());

	if (ULandscapeInfo* Info = Landscape->GetLandscapeInfo())
	{
		Info->UpdateLayerInfoMap(Landscape);
		if (RoadLayerInfo)
		{
			for (FLandscapeInfoLayerSettings& Layer : Info->Layers)
			{
				if (Layer.LayerName == RoadLayerName)
				{
					Layer.LayerInfoObj = RoadLayerInfo;
				}
			}
		}
	}
	if (!Label.IsEmpty())
	{
		Landscape->SetActorLabel(Label);
	}
	// World Partition: 遠くへ行っても地面が消えない (遠景の地形はタイルの所が空いている) よう、いつも読み込む
	if (Landscape->CanChangeIsSpatiallyLoadedFlag())
	{
		Landscape->SetIsSpatiallyLoaded(false);
	}
	Landscape->PostEditChange();
	UE_LOG(LogTemp, Display, TEXT("[FDEditorTools] ランドスケープ %s (%d x %d) を作りました"), *Label, Size, Size);
	return Landscape;
#else
	return nullptr;
#endif
}

ULandscapeLayerInfoObject* UFDEditorTools::CreateLayerInfo(const FString& PackagePath, FName LayerName)
{
#if WITH_EDITOR
	const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
	UPackage* Package = CreatePackage(*PackagePath);
	if (!Package)
	{
		UE_LOG(LogTemp, Error, TEXT("[FDEditorTools] %s を作れません"), *PackagePath);
		return nullptr;
	}
	Package->FullyLoad();
	if (ULandscapeLayerInfoObject* Existing = FindObject<ULandscapeLayerInfoObject>(Package, *AssetName))
	{
		return Existing;
	}
	ULandscapeLayerInfoObject* Info = NewObject<ULandscapeLayerInfoObject>(Package, *AssetName,
		RF_Public | RF_Standalone | RF_Transactional);
	// LayerName は版によって private なので、プロパティとして書く
	if (FNameProperty* Property = FindFProperty<FNameProperty>(ULandscapeLayerInfoObject::StaticClass(), TEXT("LayerName")))
	{
		Property->SetPropertyValue_InContainer(Info, LayerName);
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("[FDEditorTools] LandscapeLayerInfoObject に LayerName がありません"));
	}
	FAssetRegistryModule::AssetCreated(Info);
	Package->MarkPackageDirty();
	UE_LOG(LogTemp, Display, TEXT("[FDEditorTools] レイヤー情報 %s (%s) を作りました"), *PackagePath, *LayerName.ToString());
	return Info;
#else
	return nullptr;
#endif
}

bool UFDEditorTools::DisableWorldPartitionStreaming(UObject* WorldContextObject)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	UWorldPartition* WorldPartition = World ? World->GetWorldPartition() : nullptr;
	if (!WorldPartition)
	{
		UE_LOG(LogTemp, Warning, TEXT("[FDEditorTools] World Partition のレベルではありません"));
		return false;
	}
	FBoolProperty* Property = FindFProperty<FBoolProperty>(UWorldPartition::StaticClass(), TEXT("bEnableStreaming"));
	if (!Property)
	{
		UE_LOG(LogTemp, Warning, TEXT("[FDEditorTools] UWorldPartition に bEnableStreaming がありません"));
		return false;
	}
	if (Property->GetPropertyValue_InContainer(WorldPartition))
	{
		WorldPartition->Modify();
		Property->SetPropertyValue_InContainer(WorldPartition, false);
		World->GetWorldSettings()->MarkPackageDirty();
		UE_LOG(LogTemp, Display, TEXT("[FDEditorTools] World Partition のストリーミングを切りました"));
	}
	return true;
#else
	return false;
#endif
}
